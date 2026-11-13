"""Explain the actual chronological training split without reading raw seasons."""
from .compact import index


def preview(root,start,end,mixture):
    from datetime import date
    from baseball_lab.experiments.match.team_win.mixed import weights
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>last:raise ValueError('시즌 범위를 확인하세요.')
    sources=index()['mlb'];all_dates=set()
    for year in range(first.year,last.year+1):
        if str(year) not in sources:raise ValueError('선택한 MLB 시즌의 출처가 등록되지 않았습니다.')
        all_dates.update(sources[str(year)]['dates'])
    days=sorted(d for d in all_dates if start<=d<=end)
    if len(days)<3:raise ValueError('학습·중간 점검·최종 평가로 나눌 경기 날짜가 부족합니다.')
    fit_end=max(1,int(len(days)*.6));test_start=min(len(days)-1,max(2,int(len(days)*.8)))
    cutoff=days[fit_end]
    splits=[{'name':name,'start':part[0],'end':part[-1],'purpose':purpose,'game_dates':len(part)} for name,part,purpose in (
        ('학습',days[:fit_end],'실제 야구 상황의 발생 확률을 만들고 AI를 연습시킵니다.'),
        ('중간 점검',days[fit_end:test_start],'학습 중 성적을 확인합니다. 이 구간으로 발생 확률을 다시 맞추지 않습니다.'),
        ('최종 평가',days[test_start:],'학습을 끝낸 뒤 확인합니다. 학습과 중간 점검에 사용하지 않습니다.'))]
    chosen=weights(mixture) if mixture else {'MLB':1.}
    years=list(range(first.year,last.year+1));issues=[]
    league_rows=[{'league':'MLB','period':f'{start} ~ {end}',
        'use':'주자·아웃·득점이 어떻게 바뀌는지 배우는 기본 경기 기록입니다. 위의 세 구간으로 나눠 사용합니다.'}]
    lines=[f'MLB 경기 기록: {start} ~ {end}']
    if 'KBO' in chosen:
        from baseball_lab.matchup.shared import catalog
        years_kbo=[int(k.split(':')[1]) for k in catalog(root)['baselines'] if k.startswith('KBO:') and int(k.split(':')[1])<int(cutoff[:4])]
        if years_kbo:
            year=max(years_kbo)
            league_rows.append({'league':'KBO','period':f'{year} 시즌 한 시즌만 사용',
                'use':f'볼넷·삼진·안타 등의 발생 비율을 조정하는 데 사용합니다. 중간 점검이 {cutoff}에 시작하므로, 그 전에 완료된 가장 최근 시즌인 {year}년을 고릅니다. 선택한 MLB 전체 기간이 KBO에도 적용되지는 않습니다.'})
            lines.append(f'KBO: {year} 시즌')
        else:
            issues.append('중간 점검 시작 전에 완료된 KBO 시즌 기록이 없습니다.')
            league_rows.append({'league':'KBO','period':'사용할 이전 시즌 없음','use':issues[-1]})
            lines.append('KBO: 사용할 이전 시즌 없음')
    if 'NPB' in chosen:
        available=sorted(d for d in index()['npb']['daily_counts'] if d<cutoff)
        if available:
            league_rows.append({'league':'NPB','period':f'{available[0]} ~ {available[-1]}',
                'use':f'2025 정규시즌으로 확인한 경기 중 중간 점검 시작일({cutoff})보다 앞선 기록만 발생 비율 조정에 사용합니다.'})
            lines.append(f'NPB: 2025 정규시즌 중 {cutoff} 이전 경기')
        else:
            issues.append('NPB는 2025 경기 기록만 있어 현재 학습 앞 구간에 사용할 자료가 없습니다. NPB를 제외하거나 MLB 2025 시즌을 선택하세요.')
            league_rows.append({'league':'NPB','period':'학습 앞 구간에 자료 없음','use':issues[-1]})
            lines.append('NPB: 해당 기간의 앞 구간에 자료 없음 — 2025 시즌 선택 필요')
    return {'lines':lines,'calibration_cutoff_exclusive':cutoff,'splits':splits,'leagues':league_rows,
        'weights':chosen,'season_count':len(years),'selected_period':[start,end],
        'split_reason':'나중 경기의 정답을 미리 보고 배우지 않도록, 경기 날짜 순서로 나눕니다.',
        'mixture_explanation':'리그를 섞는다는 것은 같은 공격·수비 AI가 선택한 리그의 기록 특성을 번갈아 경험한다는 뜻입니다. 예를 들어 볼넷 비율이 높은 리그 환경에서는 볼넷이 상대적으로 자주 나오도록 발생 확률을 조정합니다. 주자·아웃·득점 변화의 기본 기록은 MLB 자료를 사용합니다.' if mixture else '',
        'processing_note':f'{len(years)}시즌의 경기 기록을 확인한 뒤 학습을 시작합니다. 전체 기간은 자료가 많아 단일 시즌보다 오래 걸립니다.' if len(years)>1 else '선택한 한 시즌의 경기 기록을 확인한 뒤 학습을 시작합니다.',
        'can_start':not issues,'issues':issues}
