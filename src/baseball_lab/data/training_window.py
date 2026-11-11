"""Verified collected play windows feeding the existing Match engine.

Season totals are never promoted into state/action transitions. The common
donor population is completed innings 1--8, excluding automatic runners and
walk-off censoring. Native datasets and original files are never rewritten.
"""
import csv
import json
from pathlib import Path
from datetime import date
from baseball_lab.data.lineage import checksum,content_hash,write_json
from baseball_lab.data.warehouse import local_path
from baseball_lab.data.protection import private


def sources(root):
    root=Path(root).resolve();result={}
    for path in sorted((root/'data/local/collections').glob('*/manifest.json')):
        local_path(root,path);m=json.loads(path.read_text())
        if m.get('league')!='MLB' or m.get('granularity')!='play':continue
        if m.get('source_status')!='REAL_OBSERVED' or m.get('rights_status')!='RETROSHEET_CREDIT_REQUIRED':continue
        if m.get('status')!='ACQUIRED_SCHEMA_CHECKED':continue
        year=m['season']
        if year in result and result[year]['files']!=m['files']:raise ValueError('동일 시즌의 플레이 원본 버전이 충돌합니다.')
        result[year]=m
    return result


def periods(root):
    def iso(s):return date(int(s[:4]),int(s[4:6]),int(s[6:])).isoformat()
    return {str(y):{'start':iso(m['date_range'][0]),'end':iso(m['date_range'][1])} for y,m in sources(root).items()}


def validate_window(root,start,end):
    try:first,last=date.fromisoformat(start),date.fromisoformat(end)
    except (TypeError,ValueError):raise ValueError('기록의 시작일과 종료일을 선택하세요.') from None
    limits=periods(root)
    if first>last or (last-first).days<2:raise ValueError('시작일 이후 최소 3일의 기간을 선택하세요.')
    years=list(range(first.year,last.year+1))
    if any(str(y) not in limits for y in years):raise ValueError('선택 기간에 수집되지 않은 시즌이 있습니다. 확보한 범위를 선택하세요.')
    if start<limits[str(first.year)]['start'] or end>limits[str(last.year)]['end']:raise ValueError('선택 날짜가 실제 수집 기록 범위를 벗어났습니다.')
    return start,end


def acquire(root,start,end):
    root=Path(root).resolve();validate_window(root,start,end);selected=sources(root);records=[];datasets=[];checks=[]
    from baseball_lab.r1.data import normalize
    from baseball_lab.experiments.match.team_win.half_inning import completion_aligned
    for year in range(int(start[:4]),int(end[:4])+1):
        m=selected[year];entry=next(x for x in m['files'] if x['path'].endswith('.csv'))
        path=local_path(root,root/entry['path'])
        if checksum(path)!=entry['sha256']:raise ValueError('수집 플레이 원본의 SHA-256이 다릅니다.')
        key=content_hash({'source':entry['sha256'],'adapter':'completed-innings-1-8-v1'})
        folder=local_path(root,root/'data/local/training-windows'/key);cache=folder/'dataset.json';meta=folder/'manifest.json'
        if cache.exists():
            local_path(root,cache);local_path(root,meta);metadata=json.loads(meta.read_text())
            if checksum(cache)!=metadata['sha256']:raise ValueError('학습용 정제 기록이 변경됐습니다.')
            data=json.loads(cache.read_text())
            if data['manifest']['source_version']!=entry['sha256']:raise ValueError('학습 원천 버전이 다릅니다.')
        else:
            print(f'{year}년 원본의 주자·아웃 연속성과 실제 경기 종료 날짜를 검사합니다.',flush=True)
            data=normalize(path,folder,{'source_version':entry['sha256'],'source_url':m['source_url'],'season':year},
                official=True,skip_empty_no_play=True,persist=False)
            dates={}
            with path.open(encoding='utf-8-sig',newline='') as f:
                for row in csv.DictReader(f):
                    if row['gametype']=='regular' and row['pbp']=='full':dates[row['gid']]=max(dates.get(row['gid'],''),row['date'])
            data=completion_aligned(data,dates)
            private(folder,directory=True);write_json(cache,data);write_json(meta,{'sha256':checksum(cache),'source_sha256':entry['sha256']})
        datasets.append(data['manifest']['dataset_id']);checks.append(entry['sha256'])
        records.extend(r for r in data['records'] if start<=r['date']<=end)
        del data
    if not records:raise ValueError('기간 안에 검증된 전이 기록이 없습니다.')
    manifest={'schema':'collected-training-window-v1','source_status':'REAL_OBSERVED','selected_seasons':list(range(int(start[:4]),int(end[:4])+1)),
        'original_dataset_id':content_hash({'source_csvs':checks}),
        'dataset_id':content_hash({'datasets':datasets,'start':start,'end':end,'adapter':'completed-innings-1-8-v1'}),
        'source_dataset_ids':datasets,'source_sha256':checks,'credit':m.get('credit','Retrosheet'),
        'date_semantics':'whole game aligned to last actual recorded play date','used_segments':len(records),
        'games':len({r['game_id'] for r in records}),'dates':[min(r['date'] for r in records),max(r['date'] for r in records)],
        'source_url':'https://www.retrosheet.org/downloads/plays.html',
        'donor_population':{'version':'completed-regulation-innings-1-to-8-v1'},
        'mixture_policy':'Observed MLB transitions pooled within fit only; no KBO/NPB aggregate transitions and no league-strength conversion.'}
    return {'manifest':manifest,'records':records}
