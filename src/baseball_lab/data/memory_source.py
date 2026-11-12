"""Hash-pinned official ZIPs decoded in RAM; no raw or normalized disk cache."""
import csv
import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path
from .compact import index
from .lineage import content_hash
from baseball_lab.r1.provider import OfficialRedirect


def fetch(url):
    if url not in {m['source_url'] for m in index()['mlb'].values()}:raise ValueError('확인한 공식 시즌 주소만 읽을 수 있습니다.')
    with urllib.request.build_opener(OfficialRedirect()).open(url,timeout=60) as response:
        body=response.read(32*1024*1024+1)
        if len(body)>32*1024*1024:raise ValueError('공식 배포 압축 파일 크기 한도를 넘었습니다.')
        expected=response.headers.get('Content-Length')
        if expected is not None and len(body)!=int(expected):raise ValueError('자료 수신이 중간에 끊겼습니다. 다시 시작하세요.')
        return body


def season(root,year,local=None):
    from baseball_lab.r1.data import normalize
    from baseball_lab.experiments.match.team_win.half_inning import completion_aligned
    from baseball_lab.matchup.outcome_details import classify
    m=index()['mlb'][str(year)]
    print(f'단계 1 · MLB {year} 실제 기록을 메모리에서 읽습니다. PC에 원본을 저장하지 않습니다.',flush=True)
    archives=[Path(root)/f['path'] for f in (local or {}).get('files',[]) if f['path'].endswith('.zip')]
    if archives:
        from .warehouse import local_path
        path=local_path(Path(root).resolve(),archives[0]);body=path.read_bytes()
    else:body=fetch(m['source_url'])
    if len(body)>32*1024*1024 or hashlib.sha256(body).hexdigest()!=m['zip_sha256']:raise ValueError('MLB 공식 ZIP의 SHA-256이 확인한 버전과 다릅니다.')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members=archive.infolist()
        if len(members)!=1 or members[0].filename!=f'{year}plays.csv':raise ValueError('공식 CSV 이외의 압축 경로·중복 파일을 거부했습니다.')
        info=members[0]
        if info.file_size>256*1024*1024 or info.file_size>max(1,info.compress_size)*200:raise ValueError('압축 해제 크기·압축률 한도를 넘었습니다.')
        h=hashlib.sha256()
        with archive.open(info) as f:
            while chunk:=f.read(1024*1024):h.update(chunk)
        if h.hexdigest()!=m['csv_sha256']:raise ValueError('MLB 공식 CSV의 SHA-256이 확인한 버전과 다릅니다.')
        def open_csv():return io.TextIOWrapper(archive.open(info),encoding='utf-8-sig',newline='')
        data=normalize(f'{year}plays.csv',Path(root),{'source_version':m['csv_sha256'],'source_url':m['source_url'],'season':year},
                       official=True,skip_empty_no_play=True,persist=False,regulation_rule_check=True,
                       open_csv=open_csv,parsed_sha256=m['csv_sha256'])
        dates={};labels={}
        with open_csv() as f:
            for line,r in enumerate(csv.DictReader(f),2):
                if r['gametype']!='regular' or r['pbp']!='full':continue
                dates[r['gid']]=max(dates.get(r['gid'],''),r['date'])
                if r['pa']!='1':continue
                classify(r)
                event='strikeout' if r['k']=='1' else 'walk' if r['walk']=='1' else 'hit' if any(r[k]=='1' for k in ('single','double','triple','hr')) else 'other'
                labels[f"{r['gid']}:play{r['pn']}:csvline{line}"]=event
        data=completion_aligned(data,dates)
        for row in data['records']:
            event=labels.get(row['source_row_ids'][-1])
            if event is None and not row['truncated']:raise ValueError('완료 타석 전이와 공식 사건을 연결하지 못했습니다.')
            row['common_event']=event or 'non_pa'
        # Extra labels don't alter the retained source transition identity.
        return data


def acquire(root,start,end,local):
    records=[];datasets=[];checks=[]
    years=list(range(int(start[:4]),int(end[:4])+1))
    for year in years:
        data=season(root,year,local.get(year))
        datasets.append(data['manifest']['dataset_id']);checks.append(index()['mlb'][str(year)]['csv_sha256'])
        records.extend(r for r in data['records'] if start<=r['date']<=end)
        del data
    if not records:raise ValueError('기간 안에 검증된 전이 기록이 없습니다.')
    manifest={'schema':'collected-training-window-v1','source_status':'REAL_OBSERVED','storage_mode':'memory-only',
        'selected_seasons':years,'original_dataset_id':content_hash({'source_csvs':checks}),
        'dataset_id':content_hash({'datasets':datasets,'start':start,'end':end,'adapter':'completed-innings-1-8-v1'}),
        'source_dataset_ids':datasets,'source_sha256':checks,'credit':index()['mlb'][str(years[-1])]['credit'],
        'date_semantics':'whole game aligned to last actual recorded play date','used_segments':len(records),
        'games':len({r['game_id'] for r in records}),'dates':[min(r['date'] for r in records),max(r['date'] for r in records)],
        'source_url':'https://www.retrosheet.org/downloads/plays.html',
        'donor_population':{'version':'completed-regulation-innings-1-to-8-v1'},
        'mixture_policy':'Observed MLB transitions pooled within fit only; no KBO/NPB aggregate transitions and no league-strength conversion.'}
    return {'manifest':manifest,'records':records}
