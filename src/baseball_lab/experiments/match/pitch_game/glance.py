"""At-a-glance comparison across all paired reference states."""
from html import escape
from math import isfinite
from pathlib import Path

from baseball_lab.web.styles import apply_app_styles
from .explanations import label


def build(result):
    if result.get('schema') in ('Match-pitch-decision-game-v7','Match-pitch-decision-game-v8'):
        from .report_data import build as report_data
        result=report_data(result)
    if not result.get('learning_review'):raise ValueError('이 기록은 통합 학습의 한눈에 보기를 지원하지 않습니다.')
    overview=result['overview']
    for values in overview['preferences'].values():
        for stage in ('before','after'):
            if any(type(p) not in (int,float) or not isfinite(p) or not 0<=p<=1+1e-9 for p in values[stage].values()):
                raise ValueError('전후 선호의 수치가 올바르지 않습니다. 상세 기록을 확인하세요.')
    scope=[]
    for league in result['leagues']:
        years=sorted({cohort['season'] for cohort in result['cohorts'] if cohort['league']==league})
        groups=[]
        for year in years:
            if groups and groups[-1][-1]+1==year:groups[-1].append(year)
            else:groups.append([year])
        scope.append(league+' '+', '.join(str(g[0]) if len(g)==1 else f'{g[0]}~{g[-1]}' for g in groups))
    cards=[]
    for view,executed,title,tab in (('offense','offense','공격','summary'),('defense','pitching','투구','pitch')):
        counts=overview[executed]
        top=max(counts,key=counts.get,default=None)
        cards.append({'title':title,'tab':tab,'top':label(top) if top else None,
                      'count':counts.get(top,0),'total':sum(counts.values()),'rows':overview['overall'][view][:2]})
    return {'games':overview['games'],'pitches':overview['pitches'],'scope':scope,'cards':cards,
            'completed':result['status']=='COMPLETED','checks_ok':all(all(t['checks'].values()) for t in result['teams'])}


def text(value):return escape(str(value),quote=True)


def pct(value):return f'{100*value:.1f}%'


def render(result):
    data=build(result)
    parts=['<header><a class="brand" href="/match">BaseballLab</a><a class="back" href="report.html">상세 결과 ↗</a></header>']
    scope=text(' · '.join(data['scope']))
    parts.append(f'<section class="lead"><div><h1>학습 결과 요약</h1><p class="scope">{scope}</p></div>'
                 f'<dl><div><dt>연습 경기</dt><dd>{data["games"]:,}<small> 경기</small></dd></div>'
                 f'<div><dt>전체 투구</dt><dd>{data["pitches"]:,}<small> 구</small></dd></div></dl></section>')
    if not data['completed']:parts.append('<p class="notice">중간 저장 기록</p>')
    parts.append('<section class="roles" aria-label="공격과 투구 요약">')
    for card in data['cards']:
        parts.append(f'<article class="card"><div class="card-heading"><h2>{card["title"]}</h2>'
                     f'<a href="report.html#{card["tab"]}">자세히 ↗</a></div>')
        if card['top']:
            parts.append(f'<p class="played">연습 최다 선택 <strong>{text(card["top"])}</strong>'
                         f'<span>{pct(card["count"]/card["total"])} · {card["count"]:,}회</span></p>')
        else:
            parts.append('<p class="muted">연습 기록 없음</p>')
        rows=card['rows']
        if rows:
            parts.append('<p class="scenario">전체 기준 상황의 평균 · 학습 전 → 후</p><ul class="comparisons">')
            for row in rows:
                name=text(label(row['action']))
                before=pct(row['before']);after=pct(row['after'])
                parts.append(f'<li><div class="bar-label"><span>{name}</span><span>{before} → <b>{after}</b></span></div>'
                             f'<div class="track" aria-hidden="true"><i class="before" style="width:{before}"></i></div>'
                             f'<div class="track" aria-hidden="true"><i class="after" style="width:{after}"></i></div></li>')
            parts.append('</ul>')
            lead=rows[0]
            if abs(lead['delta'])<.02:parts.append('<p class="scenario">평균 변화 폭이 2%p 미만입니다.</p>')
            if lead['up'] and lead['down']:
                parts.append(f'<p class="scenario">{text(label(lead["action"]))} 변화는 실행마다 방향이 달랐습니다.</p>')
        else:
            parts.append('<p class="scenario">전후 비교 기록 없음</p>')
        parts.append('</article>')
    parts.append('</section>')
    if not data['checks_ok']:parts.append('<p class="notice">집계를 확인해 주세요. <a href="report.html#evidence">학습 기록 ↗</a></p>')
    parts.append('<footer><a href="report.html#growth">카운트별 비교 ↗</a><a href="report.html#evidence">학습 기록 ↗</a><details class="credits"><summary>플랫폼 자료 출처</summary><p>KBO: slothman3878/kbo_playbyplay (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>), ekim56korea·NextPitchh. MLB: 공개 Statcast와 Retrosheet. NPB: This uses data sourced from the <a href="https://github.com/armstjc/Nippon-Baseball-Data-Repository">Nippon Baseball Data Repository</a>; yasumorishima/npb-stats.</p><p>The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.</p><a href="report.html#evidence">이번 실행의 상세 출처와 범위</a></details></footer>')
    template=Path(__file__).with_name('glance.html').read_text(encoding='utf-8')
    return apply_app_styles(template.replace('__CONTENT__',''.join(parts)))
