"""Hash-pinned official ZIPs decoded in RAM; no raw or normalized disk cache."""
import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
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


class DigestReader(io.RawIOBase):
    def __init__(self,stream,digest):
        super().__init__();self.stream=stream;self.digest=digest
    def readable(self):return True
    def readinto(self,buffer):
        data=self.stream.read(len(buffer));buffer[:len(data)]=data
        self.digest.update(data);return len(data)
    def close(self):
        try:self.stream.close()
        finally:super().close()


def archive_bytes(root,year,local=None):
    m=index()['mlb'][str(year)]
    archives=[Path(root)/f['path'] for f in (local or {}).get('files',[]) if f['path'].endswith('.zip')]
    if archives:
        from .warehouse import local_path
        path=local_path(Path(root).resolve(),archives[0])
        if path.stat().st_size>32*1024*1024:raise ValueError('공식 시즌 파일 크기 한도를 넘었습니다.')
        return path.read_bytes()
    return fetch(m['source_url'])


def season(root,year,local=None,*,prepared_archive=None,announce=True,game_actions=False,pitch_actions=False):
    from baseball_lab.r1.data import normalize
    from baseball_lab.experiments.match.team_win.half_inning import completion_aligned
    from baseball_lab.matchup.outcome_details import classify
    m=index()['mlb'][str(year)]
    if announce:print(f'단계 1 · MLB {year}년 경기 기록을 확인하고 있습니다.',flush=True)
    body=archive_bytes(root,year,local) if prepared_archive is None else prepared_archive
    if len(body)>32*1024*1024 or hashlib.sha256(body).hexdigest()!=m['zip_sha256']:raise ValueError('MLB 공식 ZIP의 SHA-256이 확인한 버전과 다릅니다.')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members=archive.infolist()
        if len(members)!=1 or members[0].filename!=f'{year}plays.csv':raise ValueError('공식 CSV 이외의 압축 경로·중복 파일을 거부했습니다.')
        info=members[0]
        if info.file_size>256*1024*1024 or info.file_size>max(1,info.compress_size)*200:raise ValueError('압축 해제 크기·압축률 한도를 넘었습니다.')
        digest=hashlib.sha256();opened=False;dates={};labels={};approaches={};steals=[];pitch_meta={}
        def open_csv():
            nonlocal opened
            if opened:raise ValueError('같은 시즌의 중복 읽기를 거부했습니다.')
            opened=True
            return io.TextIOWrapper(io.BufferedReader(DigestReader(archive.open(info),digest)),encoding='utf-8-sig',newline='')
        def observe(line,r):
            dates[r['gid']]=max(dates.get(r['gid'],''),r['date'])
            if game_actions:
                first=next((c for c in r['pitches'] if c in 'BCFSXHILMOPQRTVYU'),'')
                approaches[f"{r['gid']}:play{r['pn']}:csvline{line}"]='early_swing' if first in 'FSXLMOQRTY' else 'take_first' if first in 'BC' else None
                if r['pa']=='0' and any(t.startswith(('SB','CS','POCS')) for t in r['event'].split('.',1)[0].split('+')):
                    steals.append({'game_id':r['gid'],'inning':int(r['inning']),'bottom':int(r['vis_home']),'outs':int(r['outs_pre']),'bases':sum(1<<(i-1) for i in (1,2,3) if r[f'br{i}_pre']), 'outs_added':int(r['outs_post'])-int(r['outs_pre']),'end_bases':sum(1<<(i-1) for i in (1,2,3) if r[f'br{i}_post']),'runs':int(r['runs']),'record_id':f"{r['gid']}:steal:csvline{line}",'event_codes':[r['event']]})
            if r['pa']!='1':return
            if pitch_actions:pitch_meta[f"{r['gid']}:play{r['pn']}:csvline{line}"]={'pitches':r['pitches'],'pitcher':r['pitcher'],'event':'single' if r['single']=='1' else 'double' if r['double']=='1' else 'triple' if r['triple']=='1' else 'home_run' if r['hr']=='1' else 'strikeout' if r['k']=='1' else 'walk' if r['walk']=='1' else 'hbp' if r['hbp']=='1' else 'out'}
            classify(r)
            event='strikeout' if r['k']=='1' else 'walk' if r['walk']=='1' else 'hit' if any(r[k]=='1' for k in ('single','double','triple','hr')) else 'other'
            labels[f"{r['gid']}:play{r['pn']}:csvline{line}"]=event
        data=normalize(f'{year}plays.csv',Path(root),{'source_version':m['csv_sha256'],'source_url':m['source_url'],'season':year},
                       official=True,skip_empty_no_play=True,persist=False,regulation_rule_check=True,
                       open_csv=open_csv,parsed_sha256=m['csv_sha256'],observe_row=observe)
        if digest.hexdigest()!=m['csv_sha256']:raise ValueError('MLB 공식 CSV의 SHA-256이 확인한 버전과 다릅니다.')
        data=completion_aligned(data,dates)
        for row in data['records']:
            event=labels.get(row['source_row_ids'][-1])
            if event is None and not row['truncated']:raise ValueError('완료 타석 전이와 공식 사건을 연결하지 못했습니다.')
            row['common_event']=event or 'non_pa'
        if game_actions:
            halves={(r['game_id'],r['inning'],r['bottom']) for r in data['records']}
            for r in data['records']:r['approach']=approaches.get(r['source_row_ids'][0])
            data['steal_records']=[{**s,'date':f"{dates[s['game_id']][:4]}-{dates[s['game_id']][4:6]}-{dates[s['game_id']][6:]}"} for s in steals if (s['game_id'],s['inning'],s['bottom']) in halves and 0<=s['outs']<=2 and s['outs']+s['outs_added']<=3]
        if pitch_actions:data['pitch_turns']=[{**r,**pitch_meta[r['source_row_ids'][0]]} for r in data['records'] if len(r['source_row_ids'])==1 and r['source_row_ids'][0] in pitch_meta]
        # Extra labels don't alter the retained source transition identity.
        return data


def acquire(root,start,end,local,*,game_actions=False,pitch_actions=False):
    records=[];datasets=[];checks=[];steals=[];pitch_turns=[]
    years=list(range(int(start[:4]),int(end[:4])+1))
    # One future prepares only the next bounded ZIP while the current season
    # is checked. Parsing stays sequential and no inputs are written to disk.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(archive_bytes,root,years[0],local.get(years[0]))
        for position,year in enumerate(years):
            print(f'단계 1 · 경기 기록 확인 {position+1}/{len(years)}시즌 — MLB {year}년',flush=True)
            body=pending.result()
            if position+1<len(years):
                nxt=years[position+1];pending=pool.submit(archive_bytes,root,nxt,local.get(nxt))
            data=season(root,year,local.get(year),prepared_archive=body,announce=False,game_actions=game_actions,pitch_actions=pitch_actions)
            del body
            datasets.append(data['manifest']['dataset_id']);checks.append(index()['mlb'][str(year)]['csv_sha256'])
            records.extend(r for r in data['records'] if start<=r['date']<=end)
            print(f'단계 1 · {position+1}/{len(years)}시즌 확인 완료 · MLB {year}년',flush=True)
            if game_actions:steals.extend(s for s in data['steal_records'] if start<=s['date']<=end)
            if pitch_actions:pitch_turns.extend(r for r in data['pitch_turns'] if start<=r['date']<=end)
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
    result={'manifest':manifest,'records':records}
    if game_actions:
        result['steal_records']=steals
        manifest['dataset_id']=content_hash({'base':manifest['dataset_id'],'game_actions':'observed-first-pitch-and-running-v1','approaches':[(r['record_id'],r['approach']) for r in records],'steals':steals})
    if pitch_actions:
        result['pitch_turns']=pitch_turns
        manifest['dataset_id']=content_hash({'base':manifest['dataset_id'],'pitch_actions':'observed-pitch-sequence-v1','turns':pitch_turns})
    return result
