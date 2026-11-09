"""Private source registry shared by BaseballLab and EraMatch; originals stay local."""
from collections import defaultdict
import csv
import io
import json
from pathlib import Path
import threading
from zipfile import ZipFile

from baseball_lab.data.lineage import checksum,content_hash,write_json,utc_now
from baseball_lab.data.protection import private,open_private
from .models import EVENTS,distribution

LEGACY_SHA='57ab8411a07b901206b0af798d9f55a00cab79ea1d61adac492e86571b2a1058'
LEGACY_FILES=('code/KBOsimulator.py','code/kbo_batting_stats_by_season_1982-2025.csv','code/kbo_pitching_stats_by_season_1982-2025.csv')
FIELDS=('PA','AB','H','2B','3B','HR','SO','BB','HP','SH','SF','TBF')
SCHEMA='player-season-catalog-v1'
_CACHE={}
_LOCK=threading.RLock()


def source_directory(root,source):
    if source not in ('kbo-assignment','mlb-2024'):raise ValueError('등록되지 않은 자료입니다.')
    root=Path(root).resolve();directory=root/'data/local/catalog'/source
    current=root
    for part in directory.relative_to(root).parts:
        current=current/part
        if current.is_symlink():raise ValueError('선수 자료 경로에 링크를 사용할 수 없습니다.')
    if directory.exists() and any(p.is_symlink() for p in directory.iterdir()):raise ValueError('선수 자료에 링크가 포함되어 있습니다.')
    return directory


def integer(value):
    if value is None or str(value).strip() in ('','-','NA','NaN'):return None
    f=float(str(value).replace(',',''))
    if not f.is_integer() or f<0:raise ValueError('음이 아닌 정수 기록이 필요합니다.')
    return int(f)


def innings_outs(value):
    if value is None or str(value).strip()=='':return None
    parts=str(value).split('.')
    if len(parts)>2 or not parts[0].isdigit() or (len(parts)==2 and parts[1] not in ('0','1','2')):raise ValueError('이닝 소수 부분은 0·1·2아웃이어야 합니다.')
    return int(parts[0])*3+(int(parts[1]) if len(parts)==2 else 0)


def event_counts(c,role):
    n=c.get('PA' if role=='batter' else 'TBF');needed=('SO','BB','HP','H','HR','2B','3B')
    if not n or any(c.get(k) is None for k in needed):return None,'사건 분모 또는 세부 안타/사구 기록이 없습니다.'
    if c.get('AB') is not None and (c['AB']>n or c['H']>c['AB'] or c['SO']>c['AB']):return None,'타수와 안타·삼진 수가 모순입니다.'
    values=dict(zip(EVENTS,(c['SO'],c['BB'],c['HP'],c['H']-c['2B']-c['3B']-c['HR'],c['2B'],c['3B'],c['HR'],n-c['SO']-c['BB']-c['HP']-c['H'])))
    if min(values.values())<0:return None,'타석 합계와 배타적 사건 수가 모순입니다.'
    return values,None


def build_legacy(directory,source):
    profiles={};yearly_sums=defaultdict(lambda:defaultdict(int));audit={'rows':{},'merged_team_groups':0,'blocked_ambiguous_groups':0,'issues':[]}
    for role,filename in [('batter',LEGACY_FILES[1]),('pitcher',LEGACY_FILES[2])]:
        path=directory/Path(filename).name
        rows=list(csv.DictReader(io.StringIO(path.read_bytes().decode('cp949'))));audit['rows'][role]=len(rows)
        groups=defaultdict(list)
        for index,r in enumerate(rows,2):
            if not all(r.get(k) for k in ('Id','Name','Year','Team')):raise ValueError('선수 식별 필드가 없습니다.')
            c={k:integer(r.get(k)) for k in FIELDS};c['IP_OUTS']=innings_outs(r.get('IP'))
            if role=='batter':
                for k in ('PA','AB','H','SO','BB','HR','SF'):
                    if c[k] is None and k!='SF':raise ValueError('과제 리그 기준의 필수 분모가 결측입니다.')
                    yearly_sums[r['Year']][k]+=c[k] or 0
            groups[(r['Id'],r['Year'])].append((r,c,index))
        for (pid,year),items in groups.items():
            names={r['Name'] for r,_,_ in items};teams=[r['Team'] for r,_,_ in items]
            ambiguous=len(names)!=1 or len(set(teams))!=len(teams) or any(t.upper() in ('TOT','TOTAL') or '합계' in t for t in teams)
            if ambiguous:audit['blocked_ambiguous_groups']+=1
            counts={k:sum(c[k] for _,c,_ in items) if all(c[k] is not None for _,c,_ in items) else None for k in (*FIELDS,'IP_OUTS')}
            events,issue=event_counts(counts,role)
            threshold=200 if role=='batter' else 150;denominator='PA' if role=='batter' else 'TBF'
            eligible=[(r,c,i) for r,c,i in items if (c[denominator] or 0)>=threshold]
            key=f'KBO:{role}:{pid}:{year}'
            profiles[key]={'id':key,'player_id':pid,'name':items[0][0]['Name'],'season':int(year),'league':'KBO','role':role,
                           'teams':teams,'counts':counts,'events':events,'issues':[x for x in (issue,'팀 분할·합산을 확인할 수 없는 중복' if ambiguous else None) if x],
                           'legacy_row':eligible[0][1] if eligible else None,'legacy_source_row':eligible[0][2] if eligible else None,
                           'legacy_eligible':bool(eligible) and not ambiguous,'normalized_eligible':bool(events) and not ambiguous,
                           'team_rows':len(items),'status':'LEGACY_UNVERIFIED'}
            if len(items)>1:audit['merged_team_groups']+=1
    def baseline(c):
        bip=c['AB']-c['SO']-c['HR']+c['SF']
        return {'K_rate':c['SO']/max(c['PA'],1),'BB_rate':c['BB']/max(c['PA'],1),
                'HR_rate':c['HR']/max(c['PA'],1),'BABIP':(c['H']-c['HR'])/max(bip,1)}
    yearly={year:baseline(c) for year,c in yearly_sums.items()};total={k:sum(c[k] for c in yearly_sums.values()) for k in ('PA','AB','H','SO','BB','HR','SF')}
    league_counts={}
    for year in yearly:
        records=[p for p in profiles.values() if p['role']=='batter' and p['season']==int(year) and p['normalized_eligible']]
        c={e:sum(p['events'][e] for p in records) for e in EVENTS};league_counts[year]=c
    global_counts={e:sum(c[e] for c in league_counts.values()) for e in EVENTS}
    for p in profiles.values():
        if p['normalized_eligible']:p['league_rates']=distribution(league_counts[str(p['season'])])
    data={'schema':SCHEMA,'source':source,'profiles':profiles,'legacy_yearly':yearly,'legacy_all':baseline(total),
          'league_counts':league_counts,'neutral_rates':distribution(global_counts),'audit':audit,
          'models':{'legacy':{'status':'LEGACY_UNVERIFIED'},'normalized':{'status':'UNVALIDATED_COMPARISON','strength':100}},
          'default_model':'legacy'}
    return save_catalog(directory,data)


def identity(data):
    return {**{k:v for k,v in data.items() if k not in ('dataset_id','acquired_at','source')},
            'source':{k:v for k,v in data['source'].items() if k!='acquired_at'}}


def save_catalog(directory,data):
    data['dataset_id']=content_hash(identity(data))
    write_json(Path(directory)/'catalog.json',data)
    return data


def import_assignment(root,archive):
    directory=source_directory(root,'kbo-assignment')
    content=Path(archive).read_bytes() if isinstance(archive,(str,Path)) else archive
    import hashlib
    if len(content)>8*1024*1024 or hashlib.sha256(content).hexdigest()!=LEGACY_SHA:
        raise ValueError('검토한 과제 ZIP 버전이 아닙니다. 기존 자료를 바꾸지 않았습니다.')
    private(directory,directory=True)
    original=directory/'assignment-original.zip'
    if original.exists() and checksum(original)!=LEGACY_SHA:raise ValueError('보관한 과제 원본이 변경됐습니다.')
    if not original.exists():
        with open_private(original) as file:file.write(content)
    with ZipFile(io.BytesIO(content)) as z:
        members=[i for i in z.infolist() if not i.is_dir()]
        if {i.filename for i in members}!=set(LEGACY_FILES) or len(members)!=3 or any(i.file_size>8*1024*1024 for i in members):raise ValueError('과제 ZIP 구성이나 크기가 다릅니다.')
        for member in members:
            path=directory/Path(member.filename).name;raw=z.read(member)
            if path.exists() and path.read_bytes()!=raw:raise ValueError('추출한 과제 원문이 변경됐습니다.')
            if not path.exists():
                with open_private(path) as file:file.write(raw)
    source={'id':'kbo-assignment','label':'사용자가 제공한 KBO 과제 자료 · 1982~2025',
            'status':'LEGACY_UNVERIFIED','league':'KBO','source_url':None,'license':'원본 Kaggle URL·버전·재배포 허용을 독립 확인하지 못했습니다. 로컬 과제 재현용이며 공식 검증 자료가 아닙니다.',
            'archive_sha256':LEGACY_SHA,'acquired_at':utc_now(),
            'files':[{'name':p.name,'sha256':checksum(p)} for p in [original,*[directory/Path(n).name for n in LEGACY_FILES]]],
            'field_assumptions':['HP를 사구 후보로 대응합니다. 원천 정의·BB/IB 포함 관계는 미확인입니다.','결측은 개선 모델에서 0으로 채우지 않습니다.']}
    return build_legacy(directory,source)


def read_catalog(root,source):
    directory=source_directory(root,source);path=directory/'catalog.json'
    if not path.is_file():return None
    fingerprint=tuple((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted(directory.iterdir()) if p.is_file())
    with _LOCK:
        cached=_CACHE.get(str(directory))
        if cached and cached[0]==fingerprint:return cached[1]
    data=json.loads(path.read_text(encoding='utf-8'))
    check=content_hash(identity(data))
    if data.get('schema')!=SCHEMA or check!=data.get('dataset_id'):raise ValueError('선수 자료의 버전·무결성이 변경됐습니다.')
    for file in data['source']['files']:
        p=directory/file['name']
        if p.name!=file['name'] or p.is_symlink() or checksum(p)!=file['sha256']:raise ValueError('선수 원본 파일이 변경됐습니다.')
    with _LOCK:_CACHE[str(directory)]=(fingerprint,data)
    return data
