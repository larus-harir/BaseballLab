"""Collected sources through the existing player-selection and PA interface."""
from . import shared
from .catalog import event_counts
from .models import normalized,distribution,simulate,LABELS
from .reading import interpret
from baseball_lab.data.lineage import content_hash,utc_now
from baseball_lab.simulation.contracts import matchup_contract


def names(root):
    from .catalog import read_catalog
    result={}
    for year in (2023,2024):
        try:data=read_catalog(root,f'mlb-{year}')
        except (OSError,ValueError,KeyError):continue  # Never use unverifiable names.
        if data:result.update({p['player_id']:p['name'] for p in data['profiles'].values()})
    return result


def profile(row):
    events,_=event_counts({**row['counts'],'HP':row['counts'].get('HBP')},row['role'])
    fields=row.get('source_fields',{})
    return {**row,'player_id':row['source_player_id'],'status':'REAL_OBSERVED' if row['source_namespace']=='retrosheet' else 'LEGACY_UNVERIFIED',
        'teams':fields.get('teams') or [fields.get('team_label') or row.get('team') or '팀 미집계'],
        'issues':[],'legacy_eligible':False,'normalized_eligible':events is not None,'common_eligible':True,
        'events':events or row['events']}


def available(root):
    return (root/'data/local/standardized').is_dir()


def overview(root,project,*,league=None,role=None,query='',season=None):
    league=league or ('MLB' if project=='baseball' else 'KBO')
    if league not in ('MLB','KBO','NPB') or role not in (None,'batter','pitcher'):raise ValueError('리그·역할을 확인하세요.')
    if not isinstance(query,str) or len(query)>80:raise ValueError('검색어는 80자 이내입니다.')
    data=shared.catalog(root)
    all_profiles=[p for p in data['profiles'].values() if p['league']==league and shared.usable(p)]
    years=sorted({p['season'] for p in all_profiles},reverse=True)
    year=int(season) if season is not None else (years[0] if years else None)
    roster=names(root) if league=='MLB' else {}
    rows=[profile(p) for p in all_profiles if p['season']==year and (role is None or p['role']==role)
        and (not query or query.casefold() in roster.get(p['player_id'],p['name']).casefold() or query in p['player_id'])]
    rows.sort(key=lambda p:-(p['counts'].get('PA' if p['role']=='batter' else 'TBF') or 0))
    if league=='MLB':
        for p in rows:p['name']=roster.get(p['player_id'],p['name'])
    source={'id':'collected-'+league.lower(),'label':f'{league} · 수집한 선수 기록','status':'REAL_OBSERVED' if league=='MLB' else 'COMMUNITY_UNVERIFIED',
        'license':'원천별 선언 조건을 유지한 로컬 탐색용 기록','files':[]}
    full=league=='MLB'
    return {'data_mode':'collected','project':project,'league':league,'ready':bool(rows),'supported_seasons':years,'seasons':years,
        'selected_season':year,'dataset_id':data['dataset_id'],'source':source,'profiles':rows[:80],'matched':len(rows),
        'needs_connection':False,'automatic_preparation':False,
        'models':{'common':{'status':'LEAGUE_RELATIVE_ASSUMPTION'},**({'normalized':{'status':'UNVALIDATED_COMPARISON','strength':300}} if full else {})},
        'default_model':'normalized' if full else 'common','message':'보관한 수집 기록을 사용합니다.' if rows else '이 리그·시즌의 사용할 선수 기록이 없습니다.',
        'metadata':{'dataset_id':data['dataset_id'],'included_with_application':False,'provider':source['label'],
            'source_namespace':data['baselines'].get(f'{league}:{year}',{}).get('source_namespace'),
            'row_count':len(all_profiles),'capabilities':{'independent_pa':True,'pitch_actions':False}}}


def analyze(root,project,options):
    data=shared.catalog(root);b=data['profiles'].get(options.get('batter'));p=data['profiles'].get(options.get('pitcher'))
    if not b or not p or b['role']!='batter' or p['role']!='pitcher':raise ValueError('수집 기록의 타자·투수를 선택하세요.')
    if 'season' in options and options['season']!=b['season']:raise ValueError('타자 시즌과 선택한 시즌이 다릅니다.')
    if b['league']!=p['league'] or options.get('league',b['league'])!=b['league']:raise ValueError('선택한 리그의 선수 기록을 확인하세요. 다른 리그 비교는 공통 비교를 사용하세요.')
    if (project=='baseball')!=(b['league']=='MLB'):raise ValueError('리그와 프로젝트가 다릅니다.')
    b,p=profile(b),profile(p);requested=options.get('model','auto')
    if b['league']=='MLB':
        roster=names(root)
        for r in (b,p):r['name']=roster.get(r['player_id'],r['name'])
    if requested not in ('auto','normalized','common'):raise ValueError('수집 기록에서 지원하지 않는 계산 방식입니다.')
    mode=('normalized' if b['normalized_eligible'] and p['normalized_eligible'] else 'common') if requested=='auto' else requested
    target=options.get('reference',f"{b['league']}:{b['season']}")
    if mode=='common':
        result=shared.analyze(root,{**options,'reference':target})
        result.update(project=project,batter=b,pitcher=p)
        result['reading']=interpret(result);result['data_mode']='collected'
        return result
    if not b['normalized_eligible'] or not p['normalized_eligible']:raise ValueError('안타 종류·사구 기록이 부족합니다. 공통 기록 방식을 선택하세요.')
    def prior(league,year):
        rows=[profile(r) for r in data['profiles'].values() if r['league']==league and r['season']==year and r['role']=='batter']
        if not rows or any(not r['normalized_eligible'] for r in rows):raise ValueError('전체 사건의 리그 기준 기록이 부족합니다.')
        return distribution({key:sum(r['events'][key] for r in rows) for key in LABELS})
    b['league_rates']=prior(b['league'],b['season']);p['league_rates']=prior(p['league'],p['season'])
    # Frozen exploratory strength; no extrapolated predictive certification.
    model=normalized(b,p,b['league_rates'],strength=options.get('strength',300),neutral=b['league_rates'])
    import secrets
    s=simulate(model,options.get('n',25),options.get('seed',secrets.randbelow(2**31)),options.get('repetitions',200))
    source={'id':'collected-'+b['league'].lower(),'label':f"{b['league']} · 수집한 실제 선수 기록",'status':'REAL_OBSERVED',
        'license':'Retrosheet · 출처 고지 유지','files':[{'name':'수집 플레이 SHA-256','sha256':sha} for sha in sorted({b['source_sha256'],p['source_sha256']})]}
    result={'schema':'statistical-matchup-v1','project':project,'project_name':'EraMatch','created_at':utc_now(),'data_mode':'collected',
        'dataset_id':data['dataset_id'],'source':source,'batter':b,'pitcher':p,'model':model,'simulation':s,'labels':LABELS,
        'comparison':None,'validation':None,'training_executed':False,'model_status':'UNVALIDATED_COMPARISON',
        'model_selection':{'requested':requested,'selected':mode,'reason':'수집한 실제 사건 기록으로 계산했습니다. 다른 시즌으로 예측 검증 결과를 확대하지 않습니다.'},
        'scope':'선수 시즌 기록을 결합한 독립 타석 반복입니다. 검증된 경기 승률이나 구종 선택 모형은 아닙니다.'}
    result['run_id']=content_hash({'dataset_id':data['dataset_id'],'batter':b['id'],'pitcher':p['id'],'model':model,'n':s['n'],'seed':s['seed'],'repetitions':s['repetitions']})
    if options.get('expected_run_id',result['run_id'])!=result['run_id']:raise ValueError('당시 수집 자료·계산 조건과 달라 같은 대결을 재현할 수 없습니다.')
    result['contract']=matchup_contract(result)
    from .outcome_details import attach
    attach(root,result);result['reading']=interpret(result)
    return result
