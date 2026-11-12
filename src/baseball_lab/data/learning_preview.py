"""Read-only source-date preview; shares the trainer's 60/20/20 boundaries."""
from functools import lru_cache
from .catalog import DatasetCatalog
from .lineage import content_hash

@lru_cache(maxsize=32)
def dates(root,year,signature):
    games={}
    for r in DatasetCatalog(root).iter_plays(year):games[r['gid']]=max(games.get(r['gid'],''),r['date'])
    return sorted({v[:4]+'-'+v[4:6]+'-'+v[6:] for v in games.values()})

def preview(root,start,end,mixture):
    from datetime import date
    from baseball_lab.experiments.match.team_win.mixed import weights
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>last:raise ValueError('시즌 범위를 확인하세요.')
    lines=[f'MLB 전이: {start} ~ {end}']
    if not mixture:return {'lines':lines}
    chosen=weights(mixture);registry=DatasetCatalog(root);all_dates=set()
    for year in range(first.year,last.year+1):
        d=registry.describe('match',year) if year in registry.supported_seasons('match') else {'ready':False}
        if not d['ready']:
            from .compact import index
            if str(year) not in index()['mlb']:raise ValueError('선택한 MLB 시즌의 출처가 등록되지 않았습니다.')
            all_dates.update(index()['mlb'][str(year)]['dates'])
        else:all_dates.update(dates(str(registry.root),year,content_hash(d['metadata']['sha256'])))
    days=sorted(d for d in all_dates if start<=d<=end)
    if len(days)<3:raise ValueError('날짜를 나눌 실제 경기 기록이 부족합니다.')
    cutoff=days[max(1,int(len(days)*.6))]
    lines.append(f'보정에 쓸 기록: {cutoff} 이전')
    if 'KBO' in chosen:
        from baseball_lab.matchup.shared import catalog
        years=[int(k.split(':')[1]) for k in catalog(root)['baselines'] if k.startswith('KBO:') and int(k.split(':')[1])<int(cutoff[:4])]
        lines.append(f'KBO: {max(years)} 시즌' if years else 'KBO: 사용할 이전 시즌 없음')
    if 'NPB' in chosen:
        lines.append(f'NPB: 2025 정규시즌 중 {cutoff} 이전 경기' if cutoff>'2025-03-28' else 'NPB: 해당 기간의 앞 구간에 자료 없음 — 2025 시즌 선택 필요')
    return {'lines':lines,'calibration_cutoff_exclusive':cutoff}
