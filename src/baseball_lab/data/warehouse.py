"""Versioned private standardized datasets over immutable source snapshots."""
import json
import csv
from collections import defaultdict
from pathlib import Path
from baseball_lab.data.lineage import checksum,content_hash,write_json,utc_now
from baseball_lab.data.standard import COUNTS,normalize_season_row,select_window,SCHEMA
from baseball_lab.data.protection import private,open_private


def local_path(root,path):
    """Keep candidate reads/writes inside private storage without link traversal."""
    root=Path(root).resolve();path=Path(path)
    try:parts=path.relative_to(root).parts
    except ValueError:raise ValueError('자료 경로가 저장소 밖입니다.')
    current=root
    for part in parts:
        current=current/part
        if current.is_symlink():raise ValueError('자료 경로 링크를 거부했습니다.')
    resolved=path.resolve()
    if not resolved.is_relative_to(root/'data/local'):raise ValueError('자료 경로가 비공개 보관 폴더 밖입니다.')
    return resolved


def builtin_rows():
    from baseball_lab.experiments.eramatch.builtin import load_builtin,BUNDLE_SHA256
    data=load_builtin()
    for p in data['profiles'].values():
        c={k:v for k,v in p['counts'].items() if k in COUNTS}
        # HP's source definition is unverified; preserve it in source_fields.
        c.pop('HBP',None)
        row=normalize_season_row(league='KBO',season=p['season'],role=p['role'],
            source_player_id=p['player_id'],source_namespace='supplied-kbo-assignment',
            counts=c,source_sha256=BUNDLE_SHA256,missing_reasons={'HBP':'ambiguous_definition'})
        row['source_fields']={'HP':p['counts'].get('HP'),'teams':p['teams']}
        row['provenance_status']='LEGACY_UNVERIFIED'
        row['granularity']='player_season'
        yield row


def adapt_snapshot(row,manifest):
    league=row.get('league',manifest.get('league'));season=row.get('season',manifest.get('season'))
    granularity=row.get('granularity',manifest.get('granularity'))
    role=row['role']
    if role not in ('batter','pitcher','team_batting','team_pitching'):raise ValueError('알 수 없는 집계 역할입니다.')
    if granularity=='team_season':role='team_batting' if role in ('batter','team_batting') else 'team_pitching'
    raw=row['counts'];counts={k:v for k,v in raw.items() if k in COUNTS}
    if 'SAC' in raw and 'SH' not in counts:counts['SH']=raw['SAC']
    identity=row.get('source_player_id') or row.get('source_team_id')
    if not identity:raise ValueError('원천 개체 ID 없이 이름으로 개체를 만들지 않습니다.')
    normalized=normalize_season_row(league=league,season=season,role=role,
        source_player_id=identity,source_namespace=row.get('source_namespace',manifest.get('source_namespace')),
        counts=counts,source_sha256=row['source_sha256'],team=row.get('team'),
        row_kind=row.get('row_kind','season_total'),missing_reasons=row.get('missing_reasons'))
    normalized['source_fields']={**row.get('source_fields',{}),**{k:v for k,v in raw.items() if k not in COUNTS}}
    normalized['granularity']=granularity
    normalized['provenance_status']=manifest.get('source_status','UNVERIFIED')
    normalized['rights_status']=row.get('rights_status',manifest.get('rights_status','UNVERIFIED'))
    return normalized


def play_season_rows(root,manifest):
    from baseball_lab.matchup.outcome_details import classify
    files=manifest['files'];entry=next(x for x in files if x['path'].endswith('.csv'))
    path=local_path(root,Path(root).resolve()/entry['path'])
    if checksum(path)!=entry['sha256']:raise ValueError('실제 플레이 원본 지문이 다릅니다.')
    counts={role:defaultdict(lambda:dict.fromkeys(('AB','H','2B','3B','HR','SO','BB','HBP','SF','SH','PA','TBF'),0)) for role in ('batter','pitcher')}
    with path.open(encoding='utf-8-sig',newline='') as file:
        reader=csv.DictReader(file);has_ab='ab' in reader.fieldnames
        for r in reader:
            if r['gametype']!='regular' or r['pbp']!='full' or r['pa']!='1':continue
            classify(r)
            for role,idkey,den in (('batter','batter','PA'),('pitcher','pitcher','TBF')):
                c=counts[role][r[idkey]];c[den]+=1
                for field,flag in [('2B','double'),('3B','triple'),('HR','hr'),('SO','k'),('BB','walk'),('HBP','hbp'),('SF','sf'),('SH','sh')]:c[field]+=int(r[flag])
                c['H']+=sum(int(r[k]) for k in ('single','double','triple','hr'))
                if has_ab:c['AB']+=int(r['ab'])
    for role,players in counts.items():
        for player,c in players.items():
            c.pop('TBF' if role=='batter' else 'PA')
            if not has_ab:c['AB']=None
            row=normalize_season_row(league='MLB',season=manifest['season'],role=role,source_player_id=player,
                source_namespace='retrosheet',counts=c,source_sha256=entry['sha256'])
            row['granularity']='player_season'
            row['provenance_status']=manifest['source_status']
            row['rights_status']=manifest['rights_status']
            yield row


def load_snapshots(root,*,leagues=None,start=None,end=None,last_seasons=None):
    base=Path(root).resolve()/'data/local/collections'
    if base.is_symlink():raise ValueError('수집 보관 폴더의 링크는 허용하지 않습니다.')
    sources=[]
    for file in sorted(base.glob('**/manifest.json')):
        local_path(root,file)
        m=json.loads(file.read_text())
        if m.get('league') not in ('MLB','KBO','NPB'):continue
        if leagues and m['league'] not in leagues:continue
        if start is not None and m['season']<start or end is not None and m['season']>end:continue
        sources.append((file,m))
    superseded=set()
    for file,m in sources:
        if not m.get('supersedes'):continue
        prior=m['supersedes'];target=local_path(root,Path(root).resolve()/prior['manifest'])
        if target==file.resolve() or not target.is_relative_to(base):raise ValueError('정제 수정본의 이전 버전 경로가 잘못됐습니다.')
        if checksum(target)!=prior['sha256']:raise ValueError('정제 수정본의 이전 버전 지문이 다릅니다.')
        before=json.loads(target.read_text())
        if any(before.get(k)!=m.get(k) for k in ('league','season','role','granularity','source_url','source_sha256')):
            raise ValueError('정제 수정본이 서로 다른 원천을 대체할 수 없습니다.')
        superseded.add(target)
    sources=[(file,m) for file,m in sources if file.resolve() not in superseded]
    years={league:sorted({m['season'] for _,m in sources if m['league']==league})[-last_seasons:] for league in ('MLB','KBO','NPB')} if last_seasons else None
    for file,m in sources:
        if years and m['season'] not in years[m['league']]:continue
        if m.get('source_status')!='REAL_OBSERVED':raise ValueError('실제 원천으로 확인되지 않은 수집 자료입니다.')
        if m.get('league')=='MLB' and m.get('granularity')=='play':
            yield from play_season_rows(root,m);continue
        if not m.get('rows_file'):continue
        original=file.parent/m['rows_file']
        if original.is_symlink():raise ValueError('정제 파일 링크를 거부했습니다.')
        rows=local_path(root,original)
        if not rows.is_relative_to(file.parent.resolve()):raise ValueError('정제 파일 경로가 수집 폴더 밖입니다.')
        if checksum(rows)!=m['rows_sha256']:raise ValueError('수집 정제 파일 지문이 다릅니다.')
        for line in rows.read_text(encoding='utf-8').splitlines():
            if line:yield adapt_snapshot(json.loads(line),m)


def build(root,*,leagues=None,start=None,end=None,last_seasons=None,include_builtin=True):
    root=Path(root).resolve()
    select_window([],leagues=leagues,start=start,end=end,last_seasons=last_seasons)
    rows=list(load_snapshots(root,leagues=leagues,start=start,end=end,last_seasons=last_seasons))
    if include_builtin and (leagues is None or 'KBO' in leagues):rows.extend(builtin_rows())
    unique={}
    for row in rows:
        previous=unique.get(row['entity_id'])
        if previous:
            if previous['counts']!=row['counts'] or previous['missing_reasons']!=row['missing_reasons']:
                raise ValueError('같은 원천·개체·시즌의 수정본 수치가 충돌합니다. 원본 버전을 확인하세요.')
            previous['source_versions']=sorted(set(previous.get('source_versions',[previous['source_sha256']])+[row['source_sha256']]))
        else:unique[row['entity_id']]=row
    rows=list(unique.values())
    rows=select_window(rows,leagues=leagues,start=start,end=end,last_seasons=last_seasons)
    identity=content_hash(rows);folder=Path(root)/'data/local/standardized'/identity
    local_path(root,folder)
    summary={}
    for r in rows:
        item=summary.setdefault(r['league'],{'seasons':set(),'rows':0,'roles':set(),'source_namespaces':set(),'granularities':set()})
        item['seasons'].add(r['season']);item['rows']+=1;item['roles'].add(r['role']);item['source_namespaces'].add(r['source_namespace'])
        item['granularities'].add(r['granularity'])
    for item in summary.values():
        for key in ('seasons','roles','source_namespaces','granularities'):item[key]=sorted(item[key])
    manifest={'schema':SCHEMA,'dataset_id':identity,'created_at':utc_now(),'rows':len(rows),'coverage':summary,
        'selection':{'leagues':leagues,'start':start,'end':end,'last_seasons_per_league':last_seasons},
        'policy':{'missing':'null with reason; never fill absent measurements with zero',
          'identity':'provider+league+season+role+source ID; no name-only cross-league join',
          'aggregation':'Keep season context; do not mix total and team-split rows or pool rules/eras silently.',
          'learning':'No automatic policy learning from season totals. Check observed actions, states, rewards and temporal partitions.',
          'cross_league':'Requires league/rules/era/park calibration; common columns are not equivalent player ability.'}}
    if folder.exists():
        local_path(root,folder/'manifest.json');local_path(root,folder/'rows.jsonl')
        old=json.loads((folder/'manifest.json').read_text());path=folder/'rows.jsonl'
        if checksum(path)!=old['rows_sha256']:raise ValueError('기존 표준 자료가 변경됐습니다.')
        return old,folder
    private(folder,directory=True)
    with open_private(folder/'rows.jsonl') as out:
        for r in rows:out.write((json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n').encode())
    manifest['rows_sha256']=checksum(folder/'rows.jsonl');write_json(folder/'manifest.json',manifest)
    return manifest,folder
