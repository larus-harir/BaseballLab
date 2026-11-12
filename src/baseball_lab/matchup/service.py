"""One catalog and calculation boundary for both statistical applications."""
from baseball_lab.data.catalog import DatasetCatalog
from baseball_lab.data.lineage import content_hash,utc_now
from baseball_lab.simulation.contracts import matchup_contract,validate_player_season
from .models import LABELS,normalized,legacy,simulate,distribution

PROJECTS={'baseball':'BaseballLab','eramatch':'EraMatch'}


def _project(project):
    if not isinstance(project,str) or project not in PROJECTS:
        raise ValueError('선수 대결 또는 역대 선수 대결을 선택하세요.')
    return project


def _year(value,default=2024):
    if value is None:return default
    if isinstance(value,str) and value.isdigit() and len(value)==4:value=int(value)
    if type(value) is not int:raise ValueError('시즌은 실제 연도를 선택하세요.')
    return value


def source_for(project,season=2024):
    """Compatibility name: source registration belongs to DatasetCatalog."""
    _project(project)
    return DatasetCatalog('.').source_id(project,season)


def overview(root,project,*,role=None,query='',season=None,data_mode=None,league=None):
    _project(project);year=_year(season)
    if league not in (None,'MLB','KBO','NPB'):raise ValueError('리그를 확인하세요.')
    if league is not None and ((project=='baseball')!=(league=='MLB')):raise ValueError('리그와 프로젝트를 확인하세요.')
    if data_mode=='legacy' and league=='NPB':raise ValueError('NPB는 수집 기록에서 선택하세요. 다른 리그로 대체하지 않습니다.')
    if data_mode not in (None,'legacy','collected'):raise ValueError('자료 선택을 확인하세요.')
    if data_mode in (None,'collected'):
        from pathlib import Path
        from . import collected
        if collected.available(Path(root)) or league=='NPB' or (data_mode=='collected' and league in ('MLB','KBO')):
            ready=collected.overview(root,project,role=role,query=query,season=season,league=league)
            if ready['supported_seasons'] or league=='NPB':return ready
    if role not in ('batter','pitcher',None):raise ValueError('선수 역할을 확인하세요.')
    if not isinstance(query,str) or len(query)>80:raise ValueError('검색어는 80자 이내입니다.')
    registry=DatasetCatalog(root);descriptor=registry.describe(project,year)
    catalog=registry.get(project,year)
    base={**descriptor,'project':PROJECTS[project]}
    if catalog is None or not descriptor['ready']:return base
    profiles=[p for p in catalog['profiles'].values() if (role is None or p['role']==role)
              and (season is None or p['season']==year)
              and (not query or query.casefold() in p['name'].casefold() or query in p['player_id'])]
    profiles.sort(key=lambda p:-(p['counts'].get('PA' if p['role']=='batter' else 'TBF') or 0))
    return {**base,'ready':True,'dataset_id':catalog['dataset_id'],'source':catalog['source'],
            'seasons':sorted({p['season'] for p in catalog['profiles'].values()},reverse=True),
            'profiles':profiles[:80],'matched':len(profiles),'models':catalog['models'],
            'default_model':catalog['default_model'],'validation':catalog.get('validation'),
            'audit':catalog.get('audit')}


def _options_year(project,options):
    if 'season' in options:return _year(options['season'])
    # Older clients supplied only registered player IDs. Infer the catalog
    # season from the existing ID format; never substitute another year.
    batter=options.get('batter')
    if project=='baseball' and isinstance(batter,str) and batter.startswith('MLB:'):
        return _year(batter.rsplit(':',1)[-1])
    return 2024


def _select_model(catalog,b,p,requested):
    if not isinstance(requested,str):raise ValueError('계산 방식을 확인하세요.')
    if requested!='auto':
        if requested not in catalog['models']:raise ValueError('이 기록에서 지원하지 않는 계산 방식입니다.')
        return requested,'고급 설정에서 선택한 방식입니다.'
    default=catalog['default_model']
    eligible={'legacy':b.get('legacy_eligible') and p.get('legacy_eligible'),
              'normalized':b.get('normalized_eligible') and p.get('normalized_eligible'),
              'league':True}
    if eligible.get(default):
        return default,'자료와 검증 상태에 맞는 기본 방식을 선택했습니다.'
    for candidate in ('normalized','legacy'):
        if candidate in catalog['models'] and eligible[candidate]:
            return candidate,'원본 방식의 표본이 부족해, 사용 가능한 세부 사건의 비교 방식으로 계산했습니다.'
    raise ValueError('두 선수에게 공통으로 적용할 기록이 부족합니다. 다른 선수나 시즌을 고르세요.')


def analyze(root,project,options):
    _project(project)
    if not isinstance(options,dict):raise ValueError('대결 설정이 필요합니다.')
    candidate=options.get('batter')
    if options.get('data_mode')=='collected' or (options.get('data_mode') is None and isinstance(candidate,str) and len(candidate)==64 and all(c in '0123456789abcdef' for c in candidate)):
        from .collected import analyze as collected_analyze
        return collected_analyze(root,project,options)
    if options.get('data_mode')=='common':
        if project!='eramatch':raise ValueError('리그 공통 비교는 EraMatch에서 실행하세요.')
        from .shared import analyze as common_analyze
        return common_analyze(root,options)
    if not isinstance(options.get('batter'),str) or not isinstance(options.get('pitcher'),str):
        raise ValueError('타자와 투수를 모두 선택하세요.')
    year=_options_year(project,options)
    registry=DatasetCatalog(root);catalog=registry.get(project,year)
    if catalog is None:raise ValueError('선수 기록을 준비하고 있어요. 준비가 끝나면 다시 실행하세요.')
    b=catalog['profiles'].get(options['batter']);p=catalog['profiles'].get(options['pitcher'])
    cross=False
    if project=='baseball' and p is None:
        pid=options['pitcher']
        if pid.startswith('MLB:'):
            other_year=_year(pid.rsplit(':',1)[-1]);other=registry.get(project,other_year)
            if other:
                p=other['profiles'].get(pid);cross=other_year!=year
    if not b or not p or b['role']!='batter' or p['role']!='pitcher':
        raise ValueError('선택한 시즌의 타자·투수를 다시 확인하세요.')
    if project=='baseball' and b['season']!=year:raise ValueError('타자 시즌과 선택한 시즌이 다릅니다.')
    validate_player_season(b);validate_player_season(p)
    requested=options.get('model','auto');mode,reason=_select_model(catalog,b,p,requested)
    if mode=='legacy':
        if not b['legacy_eligible'] or not p['legacy_eligible']:
            raise ValueError('원본 방식은 팀별 기록에서 타자 200타석·투수 150명 이상의 표본이 필요합니다. 자동 선택이나 다른 선수를 이용하세요.')
        model=legacy(b,p,catalog['legacy_yearly'],catalog['legacy_all'])
    elif mode=='league':
        reference=distribution(catalog['league_counts'][str(b['season'])])
        model={'model':'league','version':'observed-league-v1','probabilities':reference,
               'steps':{'reference':reference},
               'assumptions':['선수 효과 없이 이 시즌 전체의 사건 비율만 사용하는 비교 기준입니다.']}
    else:
        if not b['normalized_eligible'] or not p['normalized_eligible']:
            raise ValueError('세부 안타·사구 기록이 부족하거나 합계가 모순입니다. 원본 방식 또는 다른 선수를 선택하세요.')
        strength=catalog['models']['normalized']['strength'] if project=='baseball' else options.get('strength',100)
        if type(strength) not in (int,float) or not 0<=strength<=2000:
            raise ValueError('표본 보정 강도는 0~2,000입니다.')
        model=normalized(b,p,b['league_rates'],strength=strength,
                         neutral=catalog['neutral_rates'] if project=='eramatch' else None)
    import secrets
    seed=options['seed'] if 'seed' in options else secrets.randbelow(2**31)
    simulation=simulate(model,options.get('n',25),seed,options.get('repetitions',200))
    alternative=None;comparison_error=None
    if project=='eramatch':
        try:
            if mode=='legacy':
                if not b['normalized_eligible'] or not p['normalized_eligible']:
                    raise ValueError('선택한 투수·타자의 세부 안타 사건이 부족해 개선 비교를 계산하지 않았습니다.')
                alternative=normalized(b,p,b['league_rates'],strength=options.get('strength',100),neutral=catalog['neutral_rates'])
            elif b['legacy_eligible'] and p['legacy_eligible']:
                alternative=legacy(b,p,catalog['legacy_yearly'],catalog['legacy_all'])
        except ValueError as exc:comparison_error=str(exc)
    result={'schema':'statistical-matchup-v1','project':project,'project_name':PROJECTS[project],
            'created_at':utc_now(),'dataset_id':catalog['dataset_id'],'source':catalog['source'],
            'batter':b,'pitcher':p,'model':model,'simulation':simulation,'comparison':alternative,
            'comparison_error':comparison_error,'validation':catalog.get('validation'),'labels':LABELS,
            'training_executed':False,'model_status':catalog['models'][mode]['status'],
            'model_selection':{'requested':requested,'selected':mode,'reason':reason},
            'scope':'같은 조건의 독립 타석 반복입니다. 주자·아웃·9이닝 점수·개별 투구 경로는 계산하지 않습니다.'}
    result['contract']=matchup_contract(result)
    if cross:
        result['dataset_id']=content_hash({'batter':catalog['dataset_id'],'pitcher':other['dataset_id']})
        result['validation']=None;result['model_status']='UNVALIDATED_COMPARISON'
        result['scope']='서로 다른 시즌의 리그 평균 대비 타석 기록을 비교합니다. 시즌 간 예측 검증이나 실제 경기 승률을 뜻하지 않습니다.'
        result['source']={**result['source'],'label':f'MLB {year} 타자 · {other_year} 투수','files':catalog['source']['files']+other['source']['files']}
        result['contract']=matchup_contract(result)
    if project=='eramatch':
        metadata=registry.describe(project,year)['metadata']
        if metadata['included_with_application']:
            result['data_delivery']={'kind':'application_included_season_aggregates',
                'files':metadata['sha256'],'original_files_at_runtime':False,
                'verification_scope':metadata['verification_scope']}
    # Preserve the original identity inputs for backwards reproducibility.
    result['run_id']=content_hash({'dataset_id':result['dataset_id'],'batter':b['id'],'pitcher':p['id'],
                                   'model':model,'n':simulation['n'],'seed':simulation['seed'],
                                   'repetitions':simulation['repetitions']})
    if 'expected_run_id' in options and options['expected_run_id']!=result['run_id']:
        raise ValueError('당시 자료 또는 계산 조건과 달라 같은 결과를 재현할 수 없습니다. 저장한 원래 결과는 그대로 볼 수 있습니다.')
    from .outcome_details import attach
    from .reading import interpret
    attach(root,result)
    result['reading']=interpret(result)
    return result
