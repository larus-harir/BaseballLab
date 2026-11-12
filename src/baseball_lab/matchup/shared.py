"""Common observed PA partition and explicit league-relative transport.

This is a statistical EraMatch mode, not a learned league-strength conversion.
HBP and extra-base splits are deliberately not inferred from missing fields.
"""
import json
import math
from pathlib import Path
from threading import RLock
from collections import defaultdict
from baseball_lab.data.lineage import checksum,content_hash,utc_now
from baseball_lab.data.warehouse import local_path,builtin_rows
from .models import generalized_log5,simulate

LABELS={'strikeout':'삼진','walk':'볼넷','hit':'안타 (종류 통합)','other':'나머지 결과 (사구 포함)'}
_CACHE={};_LOCK=RLock()
NPB_USE_NOTICE='NPB 공식 사이트 수집본은 2차 이용 고지에 따라 차단합니다. 별도 라이선스를 선언한 비공식 CSV는 출처별로 구분해 로컬 탐색 비교에 사용하며 upstream 권리·정확성의 독립 검증과 전략 학습 승인을 뜻하지 않습니다.'
PROVIDER_PRIORITY=('kaggle-netsong-kbo','armstjc-npb-spaia','retrosheet','supplied-kbo-assignment')


def usable(row):
    if row['league']!='NPB':return True
    return row['source_namespace']=='armstjc-npb-spaia' and row.get('rights_status')=='PUBLISHER_DECLARED_UPSTREAM_UNVERIFIED'


def partition(row):
    c=row['counts'];n=c.get('PA' if row['role']=='batter' else 'TBF')
    if type(n) is not int or n<=0 or any(type(c.get(k)) is not int or c[k]<0 for k in ('SO','BB','H')):return None
    result={'strikeout':c['SO'],'walk':c['BB'],'hit':c['H'],'other':n-c['SO']-c['BB']-c['H']}
    if min(result.values())<0:raise ValueError('공통 사건의 분모와 합계가 모순됩니다.')
    return result


def catalog(root):
    root=Path(root).resolve();candidates=[]
    for path in (root/'data/local/standardized').glob('*/manifest.json'):
        local_path(root,path);m=json.loads(path.read_text())
        # A recent-years export must never silently hide older collected data.
        if all(m.get('selection',{}).get(k) is None for k in ('leagues','start','end','last_seasons_per_league')):
            candidates.append((m.get('created_at',''),path,m))
    if candidates:
        _,path,manifest=max(candidates,key=lambda v:v[0]);rowsfile=local_path(root,path.parent/'rows.jsonl')
        fingerprint=(str(path),checksum(path),rowsfile.stat().st_size,rowsfile.stat().st_mtime_ns)
    else:
        from baseball_lab.experiments.eramatch.builtin import BUNDLE_SHA256
        manifest={'dataset_id':content_hash({'bundle':BUNDLE_SHA256,'adapter':'common-v1'}),'rows_sha256':None};fingerprint=('builtin',BUNDLE_SHA256)
    with _LOCK:
        cached=_CACHE.get(str(root))
        if cached and cached[0]==fingerprint:return cached[1]
    if candidates:
        if checksum(rowsfile)!=manifest['rows_sha256']:raise ValueError('공통 자료의 검증값이 달라졌습니다.')
        rows=[json.loads(line) for line in rowsfile.read_text().splitlines() if line]
    else:rows=list(builtin_rows())
    names={};ambiguous=set()
    from baseball_lab.experiments.eramatch.builtin import load_builtin
    for p in load_builtin()['profiles'].values():
        key=('KBO',p['season'],p['role'],p['player_id']);names[key]=p['name']
        if any('팀 분할·합산을 확인할 수 없는 중복' in issue for issue in p.get('issues',[])):ambiguous.add(key)
    # Select exactly one provider for a league/season, never add overlapping
    # copies of a player's season to inflate the reference population.
    providers=defaultdict(set);permission={}
    for row in rows:
        if row['role'] in ('batter','team_batting'):
            key=(row['league'],row['season']);ns=row['source_namespace'];providers[key].add(ns);permission[(key,ns)]=usable(row)
    def priority(key,ns):return (not permission[(key,ns)],PROVIDER_PRIORITY.index(ns) if ns in PROVIDER_PRIORITY else len(PROVIDER_PRIORITY),ns)
    selected={key:min(value,key=lambda ns:priority(key,ns)) for key,value in providers.items()}
    profiles={};baselines={};groups=defaultdict(list)
    for row in rows:
        if row['role'] not in ('batter','pitcher','team_batting'):continue
        if row['source_namespace']!=selected.get((row['league'],row['season'])):continue
        if row['source_namespace']=='supplied-kbo-assignment' and (row['league'],row['season'],row['role'],row['source_player_id']) in ambiguous:continue
        events=partition(row) if row['role']!='team_batting' else partition({**row,'role':'batter'})
        if events is None:continue
        groups[(row['league'],row['season'],row['role'])].append((row,events))
        if row['role']=='team_batting':continue
        name=row.get('source_fields',{}).get('Name') or row.get('source_fields',{}).get('選手') or names.get((row['league'],row['season'],row['role'],row['source_player_id'])) or row['source_player_id']
        profiles[row['entity_id']]={**row,'id':row['entity_id'],'player_id':row['source_player_id'],'name':name,'events':events}
    for league,year in sorted({(key[0],key[1]) for key in groups}):
        # Published team totals take priority; never sum team and player totals.
        pairs=groups.get((league,year,'team_batting')) or groups.get((league,year,'batter'),[])
        if len({r['source_namespace'] for r,_ in pairs})!=1:raise ValueError('동일 리그 기준에 다른 제공자의 중복 기록이 섞였습니다.')
        counts={k:sum(e[k] for _,e in pairs) for k in LABELS};n=sum(counts.values())
        if not n or any(v<=0 for v in counts.values()):continue
        baselines[f'{league}:{year}']={'counts':counts,'rates':{k:v/n for k,v in counts.items()},
            'source_namespace':selected[(league,year)],
            'use_allowed':all(usable(r) for r,_ in pairs),
            'basis':'team_batting' if (league,year,'team_batting') in groups else 'available_player_batting',
            'rows':len(pairs),'sample_n':n}
    data={'dataset_id':manifest['dataset_id'],'profiles':profiles,'baselines':baselines}
    with _LOCK:_CACHE[str(root)]=(fingerprint,data)
    return data


def overview(root,role=None,league=None,season=None,query=''):
    if role not in (None,'batter','pitcher') or league not in (None,'MLB','KBO','NPB'):raise ValueError('역할·리그를 확인하세요.')
    if not isinstance(query,str) or len(query)>80:raise ValueError('검색어는 80자 이내입니다.')
    if season is not None:
        try:season=int(season)
        except (TypeError,ValueError):raise ValueError('시즌을 확인하세요.') from None
    data=catalog(root)
    rows=[p for p in data['profiles'].values() if (role is None or p['role']==role) and (league is None or p['league']==league)
        and (season is None or p['season']==season) and (not query or query.casefold() in p['name'].casefold() or query.casefold() in p['player_id'].casefold())]
    rows.sort(key=lambda p:-(sum(p['events'].values())))
    return {'dataset_id':data['dataset_id'],'labels':LABELS,'references':data['baselines'],
        'profiles':rows[:80],'matched':len(rows),
        'player_sources':{role:sorted({f"{p['league']}:{p['season']}" for p in data['profiles'].values() if p['role']==role and usable(p)}) for role in ('batter','pitcher')},
        'blocked_references':[k for k,v in data['baselines'].items() if not v['use_allowed']],
        'usage_notice':NPB_USE_NOTICE,
        'scope':'공통 기록의 상대 빈도 비교 · 리그 실력 환산 검증 전'}


def analyze(root,options):
    data=catalog(root);b=data['profiles'].get(options.get('batter'));p=data['profiles'].get(options.get('pitcher'))
    if not b or not p or b['role']!='batter' or p['role']!='pitcher':raise ValueError('공통 기록이 있는 타자와 투수를 선택하세요.')
    target=options.get('reference')
    if target not in data['baselines']:raise ValueError('경기를 가정할 기준 리그·시즌을 선택하세요.')
    if not usable(b) or not usable(p) or not data['baselines'][target]['use_allowed']:raise ValueError(NPB_USE_NOTICE)
    strength=options.get('strength',100)
    if type(strength) not in (int,float) or not math.isfinite(strength) or not 0<=strength<=2000:raise ValueError('평균 보정량은 0~2,000입니다.')
    ref=data['baselines'][target]['rates'];steps={'reference':ref,'strength':strength,'target':target,'origins':{}}
    adjusted=[]
    for role,player in (('batter',b),('pitcher',p)):
        origin=f"{player['league']}:{player['season']}"
        if origin not in data['baselines']:raise ValueError('선수의 리그·시즌 기준 기록이 부족합니다.')
        prior=data['baselines'][origin]['rates'];n=sum(player['events'].values());raw={k:v/n for k,v in player['events'].items()}
        shrunk={k:(player['events'][k]+strength*prior[k])/(n+strength) for k in LABELS}
        weights={k:shrunk[k]*ref[k]/prior[k] for k in LABELS};total=sum(weights.values());value={k:v/total for k,v in weights.items()}
        steps.update({role+'_raw':raw,role+'_adjusted':value,role+'_n':n});steps['origins'][role]=data['baselines'][origin];adjusted.append(value)
    q,w,total=generalized_log5(*adjusted,ref);steps.update(weights=w,normalizer=total)
    model={'model':'common','version':'common-four-events-relative-v1','probabilities':q,'steps':steps,
        'assumptions':['각 리그·시즌 평균 대비 상대 빈도를 선택한 환경으로 옮긴다는 가정입니다. 검증된 리그 실력 환산이 아닙니다.',
            '같은 평균 대비 성적을 같은 실력으로 취급하는 가정이 남습니다. 구장·상대·수비·규칙 효과는 별도 식별하지 못했습니다.',
            '사구는 나머지에 포함하고 안타 종류는 통합합니다. 없는 피2루타·피3루타·사구를 추정하지 않습니다.',
            '시즌 합계는 전략 학습에 사용하지 않습니다. NPB 공개 기록의 학습·재배포 허용은 별도 확인 대상입니다.']}
    model['assumptions'].append('KBO 제공 자료는 원천 정의를 독립 검증하지 못했습니다. 선수 합계 기준은 확보한 선수 범위의 평균이며 공식 리그 전체 평균과 차이가 남을 수 있습니다.')
    if any(player['source_namespace']=='armstjc-npb-spaia' for player in (b,p)) or data['baselines'][target]['source_namespace']=='armstjc-npb-spaia':
        model['assumptions'].extend(['NPB는 SPAIA 출처의 비공식 배포 CSV 중 정규시즌으로 명시된 관측 경기만 집계했습니다. 공식 시즌 전체와의 일치·누락 여부는 독립 검증 전입니다.',
            'This uses data sourced from the Nippon Baseball Data Repository, which can be accessed here: https://github.com/armstjc/Nippon-Baseball-Data-Repository',
            '게시자는 데이터 사용을 선언했지만 upstream 재배포권은 독립 확인 전입니다. 로컬 탐색과 검증된 전략 학습·데이터 재배포를 구별합니다.'])
    import secrets
    simulation=simulate(model,options.get('n',25),options.get('seed',secrets.randbelow(2**31)),options.get('repetitions',200))
    identity={'dataset_id':data['dataset_id'],'batter':b['id'],'pitcher':p['id'],'model':model,
        'n':simulation['n'],'seed':simulation['seed'],'repetitions':simulation['repetitions']}
    result={'schema':'statistical-matchup-v1','project':'eramatch','project_name':'EraMatch','created_at':utc_now(),
        **{k:v for k,v in identity.items() if k in ('dataset_id',)},'batter':b,'pitcher':p,'model':model,'simulation':simulation,
        'labels':LABELS,'training_executed':False,'model_status':'LEAGUE_RELATIVE_ASSUMPTION','run_id':content_hash(identity),
        'source':{'id':'shared-standard-data','label':'수집 기록의 공통 타석 비교','status':'MIXED_PROVENANCE','files':[],
            'license':'원천별 이용 조건 유지 · 원본 및 NPB 기록 재배포 없음'},
        'scope':'독립 타석 반복입니다. 리그 간 상대 빈도 비교이며 실제 리그 간 승률·절대 실력의 검증이 아닙니다.'}
    if options.get('expected_run_id',result['run_id'])!=result['run_id']:raise ValueError('자료·기준 환경이 달라 같은 결과를 재현할 수 없습니다.')
    result['data_policy']={'events':list(LABELS),'missing_fill':False,'baseline':data['baselines'][target],
        'policy_learning':False,'absolute_league_strength_validated':False}
    return result
