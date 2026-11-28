"""A compact read-only projection of the existing learning report."""
from collections import defaultdict
from html import escape
from pathlib import Path
from math import isfinite
from baseball_lab.web.styles import apply_app_styles
from .explanations import label

AREAS=tuple(h+'_'+v for v in ('high','middle','low') for h in ('left','middle','right'))


def build(result):
    if result.get('schema') in ('Match-pitch-decision-game-v7','Match-pitch-decision-game-v8'):
        from .strategy_view import build as detailed
        result=detailed(result)
    if not result.get('learning_review'):raise ValueError('이 기록은 통합 학습의 한눈에 보기를 지원하지 않습니다.')
    o=result['overview'];stories={r['view']:r for r in o.get('explanations',[])}
    for values in o['preferences'].values():
        for stage in ('before','after'):
            if any(type(p) not in (int,float) or not isfinite(p) or not 0<=p<=1+1e-9 for p in values[stage].values()):raise ValueError('전후 선호의 수치가 올바르지 않습니다. 상세 기록을 확인하세요.')
    headline=max(stories.values(),key=lambda r:abs(r['delta']),default=None)
    per_run=defaultdict(list)
    for p in result.get('contexts',[]):
        if 'seed' in p:per_run[p['seed']].append(p['teams'][0])
    shifts=[]
    if headline and headline.get('situation_specific'):
        shifts=headline['run_deltas']
    elif headline:
        view=headline['view'];action=headline['action']
        for pairs in per_run.values():
            differences=[]
            for p in pairs:
                before,after=p[view]['before'],p[view]['after'];a,b=sum(before.values()),sum(after.values())
                if a and b:differences.append(after.get(action,0)/b-before.get(action,0)/a)
            if differences:shifts.append(sum(differences)/len(differences))
    if len(shifts)<2:interpretation='반복 실행 간 비교 기록이 부족합니다.'
    elif min(shifts)<-1e-9 and max(shifts)>1e-9:interpretation='실행마다 변화 방향이 달랐습니다.'
    elif abs(headline['delta'])<.02:interpretation='선택 확률의 평균 변화가 작았습니다.'
    elif min(shifts)>1e-9 or max(shifts)<-1e-9:interpretation='같은 상황에서 여러 실행의 선택이 같은 방향으로 변했습니다.'
    else:interpretation='변화가 없었던 실행도 있었습니다.'
    scope=[]
    for league in result['leagues']:
        years=sorted({c['season'] for c in result['cohorts'] if c['league']==league});groups=[]
        for y in years:
            if groups and groups[-1][-1]+1==y:groups[-1].append(y)
            else:groups.append([y])
        scope.append(league+' '+', '.join(str(g[0]) if len(g)==1 else f'{g[0]}~{g[-1]}' for g in groups))
    cards=[]
    for role,view,title in (('offense','offense','공격 선택'),('pitching','defense','투구 선택')):
        story=stories.get(view)
        counts=o[role];top=max(counts,key=counts.get,default=None);v=story['preferences'] if story and story.get('situation_specific') else o['preferences'][view]
        keys=sorted(v['after'].keys()|v['before'].keys(),key=lambda k:(-abs(v['after'].get(k,0)-v['before'].get(k,0)),k))
        if story and abs(story['delta'])>=.02 and story.get('comparison'):
            keys=[item['action'] for item in story['comparison']]
        rows=[{'action':k,'before':v['before'].get(k,0),'after':v['after'].get(k,0)} for k in keys[:2]]
        cards.append({'role':view,'title':title,'top':label(top) if top else None,'count':counts.get(top,0) if top else 0,'total':sum(counts.values()),
                      'story':story if o['games'] else None,
                      'detail':(stories.get('direction',{}).get('summary','') if view=='offense' else '') if o['games'] else '',
                      'rows':rows,'states':v['states'] if o['games'] else 0})
    return {'schema':'learning-glance-v1','headline':'이번 학습의 선택 변화' if headline and o['games'] else '아직 비교할 학습 기록이 없습니다.',
        'games':o['games'],'pitches':o['pitches'],'completed':result['status']=='COMPLETED','scope':scope,'cards':cards,
        'course':o['preferences']['course'] if o['games'] else {'states':0},'interpretation':interpretation,
        'featured':headline,
        'checks_ok':all(all(t['checks'].values()) for t in result['teams']),
        'source_asset':result['evidence']['asset_sha256']}


def text(value):return escape(str(value),quote=True)
def pct(value):return f'{100*value:.1f}%'


def course_grid(values,scale,title):
    cells=[]
    for i,area in enumerate(AREAS):
        v=values.get('area:'+area,0);intensity=v/scale if scale else 0
        rgb=tuple(round(a+(b-a)*intensity) for a,b in zip((241,246,242),(14,100,88)))
        # Relative luminance chooses accessible foreground on the shared scale.
        linear=[c/255/12.92 if c/255<=.04045 else ((c/255+.055)/1.055)**2.4 for c in rgb]
        lum=sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)));ink='#fff' if 1.05/(lum+.05)>=4.5 else '#000'
        x,y=8+92*(i%3),8+66*(i//3)
        cells.append(f'<g><title>{text(label("area:"+area))}: {pct(v)}</title><rect x="{x}" y="{y}" width="87" height="61" rx="7" fill="rgb{rgb}"/><text x="{x+43}" y="{y+35}" text-anchor="middle" fill="{ink}">{pct(v)}</text></g>')
    accessible=' / '.join(label('area:'+a)+' '+pct(values.get('area:'+a,0)) for a in AREAS)
    return f'<figure><figcaption>{text(title)}</figcaption><svg viewBox="0 0 288 210" role="img" aria-label="{text(title+": "+accessible)}">'+''.join(cells)+'</svg></figure>'


def render(result):
    d=build(result);parts=[]
    parts.append('<header><a class="brand" href="/match">BaseballLab <span>/ Match</span></a><a class="back" href="report.html">상세 결과로 돌아가기 ↗</a></header>')
    state='학습 결과' if d['completed'] else '중간 저장 기록'
    parts.append(f'<section class="lead"><div><p class="eyebrow">한눈에 보기 · {state}</p><h1>{text(d["headline"])}</h1><p class="scope">{text(" · ".join(d["scope"]))}</p></div><dl><div><dt>저장된 연습</dt><dd>{d["games"]:,}<small> 경기</small></dd></div><div><dt>선택한 투구</dt><dd>{d["pitches"]:,}<small> 구</small></dd></div></dl></section>')
    if not d['completed']:parts.append('<p class="notice">학습 도중 저장된 내용입니다. 최종 결과와 다를 수 있습니다.</p>')
    parts.append('<div class="legend"><span><i class="before"></i>학습 전</span><span><i class="after"></i>학습 후</span><span>같은 상황의 선택 확률</span></div><section class="roles" aria-label="공격과 투구 요약">')
    for c in d['cards']:
        parts.append(f'<article class="card"><div class="card-heading"><h2>{text(c["title"])}</h2><a href="report.html#{"pitch" if c["role"]=="defense" else "summary"}">자세히 ↗</a></div>')
        if c['story']:
            parts.append('<p class="story">'+text(c['story'].get('brief',c['story']['summary']))+'</p>')
            if c['story'].get('brief_state'):parts.append('<p class="scenario">'+text(c['story']['brief_state'])+'</p>')
        if c['states']:
            parts.append('<ul class="comparisons">')
            for row in c['rows']:
                name=label(row['action'])
                aria=f'{name}: 학습 전 {pct(row["before"])}, 학습 후 {pct(row["after"])}'
                parts.append(f'<li aria-label="{text(aria)}"><div class="bar-label"><span>{text(name)}</span><span>{pct(row["before"])} → <b>{pct(row["after"])}</b></span></div><div class="track"><i class="before" style="width:{100*row["before"]:.5f}%"></i></div><div class="track"><i class="after" style="width:{100*row["after"]:.5f}%"></i></div></li>')
            parts.append('</ul>')
        else:parts.append('<p class="empty">전후 비교 기록이 없습니다.</p>')
        parts.append('</article>')
    parts.append('</section>')
    parts.append('<section class="bottom"><article class="card course"><div class="card-heading"><h2>코스 선택 변화</h2><a href="report.html#pitch">투구 상세 ↗</a></div>')
    course=d['course']
    if course['states']:
        scale=max([*course['before'].values(),*course['after'].values()],default=0)
        parts.append('<div class="grids">'+course_grid(course['before'],scale,'학습 전')+course_grid(course['after'],scale,'학습 후')+'</div><p class="caption">코스를 정한 투구의 평균 선택 확률 · 같은 색상 기준 · 존 밖 포함</p>')
    else:parts.append('<p class="empty">이 기록에는 코스 선택의 전후 비교가 없습니다.</p>')
    parts.append('</article><article class="card interpretation"><h2>가장 큰 변화</h2>')
    if d['featured']:
        featured=d['featured']
        parts.append('<p class="story">'+text(featured.get('brief',featured['summary']))+'</p>')
        if featured.get('brief_state'):parts.append('<p class="scenario">'+text(featured['brief_state'])+'</p>')
    parts.append('<p>'+text(d['interpretation'])+'</p>')
    if not d['checks_ok']:parts.append('<p class="notice">선택·투구 집계에 확인이 필요한 항목이 있습니다. 상세 근거를 먼저 확인하세요.</p>')
    parts.append('<p class="limit">승률 향상은 별도 평가가 필요합니다.</p><a href="report.html#evidence">학습 근거 ↗</a></article></section>')
    if any(c['story'] for c in d['cards']):
        parts.append('<details class="card story-evidence"><summary>상황·근거</summary><div class="roles">')
        for c in d['cards']:
            story=c['story']
            if not story:continue
            parts.append('<div><h3>'+text(c['title'])+'</h3><p>'+text(story['summary'])+'</p><p>'+text(story['context'])+'</p><p>'+text(story['reason'])+'</p>')
            if c['detail']:parts.append('<p>'+text(c['detail'])+'</p>')
            if c['top']:parts.append(f'<p class="played">전체 연습의 최다 선택 <strong>{text(c["top"])}</strong><span>{c["count"]:,} / {c["total"]:,}회</span></p>')
            parts.append('</div>')
        parts.append('</div></details>')
    parts.append('<footer><span>자료와 상세 결과는 동일</span><a href="report.html#growth">학습 변화 ↗</a><details class="credits"><summary>플랫폼 자료 출처</summary><p>KBO: slothman3878/kbo_playbyplay (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>), ekim56korea·NextPitchh. MLB: 공개 Statcast와 Retrosheet. NPB: This uses data sourced from the <a href="https://github.com/armstjc/Nippon-Baseball-Data-Repository">Nippon Baseball Data Repository</a>; yasumorishima/npb-stats.</p><p>The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.</p><a href="report.html#evidence">이번 실행의 상세 출처와 범위</a></details></footer>')
    template=Path(__file__).with_name('glance.html').read_text(encoding='utf-8')
    return apply_app_styles(template.replace('__CONTENT__',''.join(parts)))
