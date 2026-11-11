"""Collect official multi-season candidates without changing production models."""
from pathlib import Path
import sys,argparse,json,csv,secrets
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from baseball_lab.data.league_sources import fetch,parse_npb,parse_npb_players
from baseball_lab.data.lineage import checksum,write_json,utc_now
from baseball_lab.data.protection import private,open_private
from baseball_lab.r1.provider import extract_csv,TERMS_URL
ROOT=Path(__file__).resolve().parents[1]


def new_dir(root,league,year,kind):
    directory=root/'data/local/collections'/f'{league.lower()}-{year}-{kind}-{secrets.token_hex(4)}'
    # Fixed relative storage tree; reject links rather than escape root.
    cur=root
    for part in directory.relative_to(root).parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('수집 경로 링크 거부')
        cur.mkdir(mode=0o700,exist_ok=True)
    private(directory,directory=True);return directory


def save_rows(directory,rows,meta):
    target=directory/'rows.jsonl'
    with open_private(target) as f:
        for row in rows:f.write((json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n').encode())
    manifest={'schema':'league-source-snapshot-v1','status':'ACQUIRED_PARSED','acquired_at':utc_now(),
        'rows_file':'rows.jsonl','rows_sha256':checksum(target),'row_count':len(rows),
        'training_registered':False,'probability_model_changed':False,**meta}
    write_json(directory/'manifest.json',manifest);return manifest


def reusable_manifest(root,url):
    """Reuse a verified local snapshot; never modify its files."""
    snapshots={path:json.loads(path.read_text()) for path in sorted((root/'data/local/collections').glob('*/manifest.json'))}
    superseded=set()
    for meta in snapshots.values():
        prior=meta.get('supersedes')
        if not prior:continue
        old=root/prior['manifest']
        if old not in snapshots or checksum(old)!=prior['sha256']:raise ValueError('이전 스냅샷 대체 지문 불일치')
        if any(snapshots[old].get(k)!=meta.get(k) for k in ('league','season','role','granularity','source_url','source_sha256')):
            raise ValueError('서로 다른 원천의 스냅샷 대체 거부')
        superseded.add(old)
    for path,meta in snapshots.items():
        if path in superseded:continue
        if meta.get('source_url')!=url:continue
        checks=[]
        if meta.get('raw_file'):checks.append((path.parent/meta['raw_file'],meta['source_sha256']))
        if meta.get('rows_file'):checks.append((path.parent/meta['rows_file'],meta['rows_sha256']))
        checks.extend((root/item['path'],item['sha256']) for item in meta.get('files',[]))
        for candidate,expected in checks:
            if not candidate.resolve().is_relative_to(root):raise ValueError('스냅샷 경로 이탈')
            if checksum(candidate)!=expected:raise ValueError('기존 스냅샷 해시 불일치')
        if checks:return meta
    return None


def npb(root,year,role,conference):
    url=f'https://npb.jp/bis/{year}/stats/tm{"b" if role=="batter" else "p"}_{conference}.html'
    cached=reusable_manifest(root,url)
    if cached:return cached
    directory=new_dir(root,'NPB',year,role+'-'+conference)
    page=directory/'source.html';fetch(url,page);fingerprint=checksum(page)
    text=page.read_bytes().decode('utf-8')
    if str(year) not in text:raise ValueError('원천 시즌 확인 실패')
    rows=parse_npb(text,year,role,conference,fingerprint)
    return save_rows(directory,rows,{'league':'NPB','season':year,'role':role,'granularity':'team_season',
        'source_namespace':'npb-official','source_url':url,'source_sha256':fingerprint,
        'rights_status':'PUBLIC_PAGE_REUSE_UNVERIFIED','source_status':'REAL_OBSERVED',
        'raw_file':'source.html','subleague':conference,'redistribution_allowed':False,
        'limitations':['Team season aggregates are not player or pitch records.','Reuse/automated-training licensing is not independently granted.','Missing fields remain missing; pitching 2B/3B/AB are not inferred.']})


def npb_players(root,year,role,team):
    url=f'https://npb.jp/bis/{year}/stats/id{"b" if role=="batter" else "p"}1_{team}.html'
    cached=reusable_manifest(root,url)
    if cached:return cached
    directory=new_dir(root,'NPB',year,'players-'+role+'-'+team)
    page=directory/'source.html';fetch(url,page);fingerprint=checksum(page)
    text=page.read_text()
    if f'{year}年度' not in text:raise ValueError('NPB 선수 원천 시즌 확인 실패')
    rows=parse_npb_players(text,year,role,team,fingerprint)
    return save_rows(directory,rows,{'league':'NPB','season':year,'role':role,'granularity':'player_season_team',
        'source_namespace':'npb-official-name-only','source_url':url,'source_sha256':fingerprint,
        'rights_status':'PUBLIC_PAGE_REUSE_UNVERIFIED','source_status':'REAL_OBSERVED',
        'raw_file':'source.html','team':team,'redistribution_allowed':False,
        'identity_status':'ROW_SCOPED_NAME_ONLY_NOT_VERIFIED_PERSON_ID',
        'limitations':['Team table includes non-qualified players; no claim of all registered players.',
            'No official stable player ID provided: local row IDs cannot link people across teams, years or roles.',
            'Reuse/automated-training licensing is not independently granted.',
            'Missing pitching AB/2B/3B remain missing. Team splits are never treated as whole-season totals.']})


def mlb(root,year,notice):
    url=f'https://www.retrosheet.org/downloads/plays/{year}plays.zip'
    if url not in notice:raise ValueError('공식 고지에 시즌 배포 링크 없음')
    cached=reusable_manifest(root,url)
    if cached:return cached
    directory=new_dir(root,'MLB',year,'plays');archive=directory/f'{year}plays.zip';parsed=directory/f'{year}plays.csv'
    existing=list((root/'data/local/retrosheet').glob(f'*/{year}plays.zip'))
    # Existing registered/candidate original is read, never copied over or changed.
    if existing:
        archive=existing[0]
        existing_csv=archive.with_suffix('.csv')
        if existing_csv.exists():parsed=existing_csv
    else:fetch(url,archive,32*1024*1024)
    if not parsed.exists():extract_csv(archive,parsed,year)
    pa=0;plays=0;seen=set();first=None;last=None;fields=None
    with parsed.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames
        required={'gid','pn','pa','batter','pitcher','gametype','pbp','date','single','double','triple','hr','walk','hbp','k'}
        if not fields or not required.issubset(fields):raise ValueError('MLB 원천 열 부족')
        for row in reader:
            if row['gametype']!='regular' or row['pbp']!='full':continue
            plays+=1;first=min(first or row['date'],row['date']);last=max(last or row['date'],row['date'])
            if row['pa']!='1':continue
            key=(row['gid'],row['pn'])
            if key in seen:raise ValueError('중복 타석 ID')
            seen.add(key);pa+=1
    meta={'schema':'league-source-snapshot-v1','status':'ACQUIRED_SCHEMA_CHECKED','league':'MLB','season':year,
        'granularity':'play','acquired_at':utc_now(),'source_namespace':'retrosheet','source_url':url,
        'rights_status':'RETROSHEET_CREDIT_REQUIRED','source_status':'REAL_OBSERVED',
        'training_registered':False,'probability_model_changed':False,'row_count':plays,'completed_pa':pa,
        'date_range':[first,last],'fields':fields,'files':[{'path':str(archive.relative_to(root)),'sha256':checksum(archive)}, {'path':str(parsed.relative_to(root)),'sha256':checksum(parsed)}],
        'limitations':['Raw collection/schema checks are not transition-model or predictive validation.'],
        'credit':'The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.'}
    write_json(directory/'manifest.json',meta);return meta


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--start-year',type=int,default=2015);p.add_argument('--end-year',type=int,default=2025);p.add_argument('--leagues',nargs='+',choices=['MLB','NPB'],default=['MLB','NPB']);p.add_argument('--npb-players',action='store_true',help='NPB 12구단 선수별 시즌 표 추가 수집');a=p.parse_args()
    if not 1871<=a.start_year<=a.end_year<=datetime.now(timezone.utc).year:p.error('1871년~현재 연도 범위; 공식 배포 링크가 있는 시즌만 수집')
    if 'NPB' in a.leagues and a.start_year<1950:p.error('NPB 양대 리그 수집은 1950년 이후만 지원')
    root=a.root.resolve();results=[];failures=[];jobs=[]
    if 'MLB' in a.leagues:
        directory=new_dir(root,'MLB',a.end_year,'notice');page=directory/'source-notice.html';fetch(TERMS_URL,page);notice=page.read_text()
        if 'free to make any desired use' not in notice or 'copyrighted by Retrosheet' not in notice:raise ValueError('Retrosheet 이용 고지 확인 실패')
        for year in range(a.start_year,a.end_year+1):jobs.append((mlb,(root,year,notice)))
    if 'NPB' in a.leagues:
        for year in range(a.start_year,a.end_year+1):
            for role in ['batter','pitcher']:
                for conference in ['c','p']:jobs.append((npb,(root,year,role,conference)))
            if a.npb_players:
                for role in ['batter','pitcher']:
                    for team in ['g','t','db','c','s','d','h','f','m','e','l','b']:
                        jobs.append((npb_players,(root,year,role,team)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(fn,*args):(fn.__name__,args[1:]) for fn,args in jobs}
        for future in as_completed(futures):
            try:
                result=future.result();results.append(result);print(result['league'],result['season'],result.get('role','plays'),result['row_count'],flush=True)
            except Exception as e:
                failures.append({'job':str(futures[future]),'error':str(e)});print('FAILED',failures[-1],flush=True)
    summary={'schema':'league-collection-run-v1','finished_at':utc_now(),'acquired':results,'failures':failures}
    output=root/'data/local/collections'/('collection-run-'+secrets.token_hex(4)+'.json');write_json(output,summary)
    print('Manifest:',output,flush=True)
    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
