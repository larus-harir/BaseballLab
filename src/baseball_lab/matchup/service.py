"""One probability engine and catalog used by both statistical applications."""
from pathlib import Path
from baseball_lab.data.lineage import content_hash,utc_now
from .catalog import read_catalog
from .models import EVENTS,LABELS,normalized,legacy,simulate,distribution

PROJECTS={'baseball':'BaseballLab','eramatch':'EraMatch'}


def source_for(project):
    if not isinstance(project,str) or project not in PROJECTS:raise ValueError('지원하는 프로젝트를 선택하세요.')
    return 'mlb-2024' if project=='baseball' else 'kbo-assignment'


def overview(root,project,*,role=None,query='',season=None):
    source=source_for(project);catalog=read_catalog(root,source)
    if catalog is None:
        return {'ready':False,'project':PROJECTS[project],'source_id':source,
                'message':'공식 MLB 선수 기록을 자동으로 준비할 수 있습니다.' if project=='baseball' else '과제 ZIP이 연결되지 않았습니다. 원본 파일을 한 번 연결하면 이후에는 보관 자료를 재사용합니다.'}
    if role not in ('batter','pitcher',None):raise ValueError('선수 역할을 확인하세요.')
    if len(query)>80:raise ValueError('검색어는 80자 이내입니다.')
    profiles=[p for p in catalog['profiles'].values() if (role is None or p['role']==role)
              and (not season or p['season']==int(season)) and (not query or query.casefold() in p['name'].casefold() or query in p['player_id'])]
    profiles.sort(key=lambda p:-(p['counts'].get('PA' if p['role']=='batter' else 'TBF') or 0))
    return {'ready':True,'project':PROJECTS[project],'source_id':source,'dataset_id':catalog['dataset_id'],
            'source':catalog['source'],'seasons':sorted({p['season'] for p in catalog['profiles'].values()},reverse=True),
            'profiles':profiles[:80],'matched':len(profiles),'models':catalog['models'],'default_model':catalog['default_model'],
            'validation':catalog.get('validation'),'audit':catalog.get('audit')}


def analyze(root,project,options):
    if not isinstance(options,dict):raise ValueError('대결 설정이 필요합니다.')
    catalog=read_catalog(root,source_for(project))
    if catalog is None:raise ValueError('선수 기록을 먼저 준비하세요.')
    if not isinstance(options.get('batter'),str) or not isinstance(options.get('pitcher'),str):raise ValueError('선수 ID가 필요합니다.')
    b=catalog['profiles'].get(options.get('batter'));p=catalog['profiles'].get(options.get('pitcher'))
    if not b or not p or b['role']!='batter' or p['role']!='pitcher':raise ValueError('등록된 타자·투수 프로필을 선택하세요.')
    mode=options.get('model',catalog['default_model'])
    if not isinstance(mode,str) or mode not in catalog['models']:raise ValueError('이 자료에서 지원하지 않는 계산 방식입니다.')
    if project=='baseball' and b['season']!=p['season']:raise ValueError('기본 대결은 같은 시즌입니다. 다른 시대는 EraMatch에서 선택하세요.')
    if mode=='legacy':
        if not b['legacy_eligible'] or not p['legacy_eligible']:raise ValueError('과제 원본의 최소 타석/상대 타자 수 또는 중복 검사를 만족하지 못했습니다.')
        model=legacy(b,p,catalog['legacy_yearly'],catalog['legacy_all'])
    elif mode=='league':
        model={'model':'league','version':'observed-league-v1','probabilities':distribution(catalog['league_counts'][str(b['season'])]),'steps':{'reference':distribution(catalog['league_counts'][str(b['season'])])},'assumptions':['선수 효과 없이 이 시즌 전체의 사건 비율만 사용하는 비교 기준입니다.']}
    else:
        if not b['normalized_eligible'] or not p['normalized_eligible']:raise ValueError('정규화 비교에 필요한 세부 사건이 결측 또는 모순입니다. 0으로 채우지 않았습니다.')
        strength=catalog['models']['normalized']['strength'] if project=='baseball' else options.get('strength',100)
        if type(strength) not in (int,float) or not 0<=strength<=2000:raise ValueError('비교 모델의 보정 강도는 0~2,000입니다.')
        model=normalized(b,p,b['league_rates'],strength=strength,neutral=catalog['neutral_rates'] if project=='eramatch' else None)
    simulation=simulate(model,options.get('n',25),options.get('seed',41),options.get('repetitions',200))
    alternative=None;comparison_error=None
    if project=='eramatch':
        try:
            if mode=='legacy':
                if not b['normalized_eligible'] or not p['normalized_eligible']:raise ValueError('선택한 투수·타자의 세부 안타 사건이 부족해 개선 비교를 계산하지 않았습니다.')
                alternative=normalized(b,p,b['league_rates'],strength=options.get('strength',100),neutral=catalog['neutral_rates'])
            elif b['legacy_eligible'] and p['legacy_eligible']:alternative=legacy(b,p,catalog['legacy_yearly'],catalog['legacy_all'])
        except ValueError as exc:comparison_error=str(exc)
    source=catalog['source'];result={'schema':'statistical-matchup-v1','project':project,'project_name':PROJECTS[project],
             'created_at':utc_now(),'dataset_id':catalog['dataset_id'],'source':source,'batter':b,'pitcher':p,
             'model':model,'simulation':simulation,'comparison':alternative,'comparison_error':comparison_error,
             'validation':catalog.get('validation'),'labels':LABELS,'training_executed':False,'model_status':catalog['models'][mode]['status'],
             'scope':'가상 타석 반복입니다. 실제 경기 기록이나 9이닝 경기 점수, 개별 투구 경로를 재현하지 않습니다.'}
    result['run_id']=content_hash({'dataset_id':catalog['dataset_id'],'batter':b['id'],'pitcher':p['id'],
                                   'model':model,'n':simulation['n'],'seed':simulation['seed'],'repetitions':simulation['repetitions']})
    return result
