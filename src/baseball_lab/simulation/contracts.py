"""Shared simulation metadata without equating PA draws and contextual games.

Adapters preserve older stored formats. This validates the common boundary;
probability estimation and baseball rules remain in their existing modules.
"""
from collections.abc import Mapping

from baseball_lab.evaluation.sabermetrics import validate_probability_distribution

CONTRACT_SCHEMA='baseball-simulation-contract-v1'
ENGINE_VERSION='baseball-shared-simulation-v1'
EVENTS=('strikeout','walk','hbp','single','double','triple','home_run','other')


def validate_player_season(profile):
    """Check an existing profile without rewriting source or derived records."""
    required=('id','player_id','name','season','league','role','counts','status')
    if not isinstance(profile,Mapping) or any(key not in profile for key in required):
        raise ValueError('선수의 식별자·시즌·기록 정보가 부족합니다.')
    if any(not isinstance(profile[key],str) or not profile[key] for key in ('id','player_id','name','league')):
        raise ValueError('선수 식별 정보를 확인하세요.')
    if type(profile['season']) is not int or not 1800<=profile['season']<=2200:
        raise ValueError('실제 선수 시즌을 확인하세요.')
    if profile['role'] not in ('batter','pitcher') or not isinstance(profile['counts'],Mapping):
        raise ValueError('선수 역할과 기록을 확인하세요.')
    if profile['status'] not in ('REAL_OBSERVED','LEGACY_UNVERIFIED','MOCK_TEST_ONLY'):
        raise ValueError('선수 자료의 확인 상태가 없습니다.')
    for value in profile['counts'].values():
        if value is not None and (type(value) is not int or value<0):
            raise ValueError('선수 기록은 결측 또는 음이 아닌 정수여야 합니다.')
    denominator='PA' if profile['role']=='batter' else 'TBF'
    n=profile['counts'].get(denominator)
    if type(n) is not int or n<=0:
        raise ValueError('선수 기록의 실제 타석 분모가 없습니다.')
    if profile.get('normalized_eligible'):
        counts=profile.get('events')
        if not isinstance(counts,Mapping) or set(counts)!=set(EVENTS):
            raise ValueError('선수 사건 정의가 공통 규격과 다릅니다.')
        if any(type(value) is not int or value<0 for value in counts.values()) or sum(counts.values())!=n:
            raise ValueError('선수 사건 합계와 실제 타석 분모가 다릅니다.')
    return profile


def validate_outcomes(probabilities):
    if not isinstance(probabilities,Mapping) or set(probabilities)!=set(EVENTS):
        raise ValueError('겹치지 않는 전체 타석 사건이 필요합니다.')
    validate_probability_distribution(probabilities)
    return probabilities


def matchup_contract(analysis):
    """Canonical metadata used by both BaseballLab and EraMatch results."""
    b=validate_player_season(analysis['batter']);p=validate_player_season(analysis['pitcher'])
    model=analysis['model'];simulation=analysis['simulation']
    validate_outcomes(model['probabilities'])
    events=simulation['events'];n=simulation['n']
    if type(n) is not int or n<=0 or len(events)!=n or any(e not in EVENTS for e in events):
        raise ValueError('가상 타석 기록과 반복 횟수가 다릅니다.')
    if simulation['counts']!={e:events.count(e) for e in EVENTS}:
        raise ValueError('타석별 기록과 결과 집계가 다릅니다.')
    legacy=model['model']=='legacy';steps=model['steps']
    return {'schema':CONTRACT_SCHEMA,'engine_version':ENGINE_VERSION,'mode':'independent_pa',
            'model_version':model['version'],'dataset_ids':[analysis['dataset_id']],
            'source_status':analysis['source']['status'],
            'probability_status':'LEGACY_UNVERIFIED' if legacy else 'EMPIRICALLY_ESTIMATED',
            'result_status':'MODEL_SIMULATED','assumptions':list(model['assumptions']),
            'prediction_scope':analysis['scope'],'random_seed':simulation['seed'],
            'simulation_count':n,'repetitions':simulation['repetitions'],
            'coverage':{'batter_n':steps.get('batter_n',b['counts'].get('PA')),
                        'pitcher_n':steps.get('pitcher_n',p['counts'].get('TBF')),
                        'modeled_events':[e for e in EVENTS if e!='hbp' or not legacy],
                        'partition_complete':True,'hbp_modeled':not legacy},
            'uncertainty':{'sampling':simulation['uncertainty'],'data_uncertainty_estimated':False,
                           'model_uncertainty_estimated':False},
            'model_limitations':['독립 타석의 반복이며 주자·아웃·9이닝 점수를 이어 계산하지 않습니다.',
                                 '관측 기록 결합은 미선택 행동의 인과효과나 순수 선수 능력을 입증하지 않습니다.']}


def observation_contract(result):
    """The same metadata envelope for the preserved contextual observer.

    A recorded trace has no per-event categorical probabilities. Expose that
    limitation explicitly instead of inventing a distribution to fit this API.
    """
    observed=result['source_status']=='REAL_OBSERVED'
    return {'schema':CONTRACT_SCHEMA,'engine_version':ENGINE_VERSION,'mode':'contextual_trace',
            'model_version':'observed-turn-v1' if observed else 'r1-observation-adapter-v1',
            'dataset_ids':[result['dataset_id']],'source_status':result['source_status'],
            'result_status':result['source_status'],'assumptions':[] if observed else [
                '비슷한 관측 상황의 플레이 묶음을 새 선택에 적용한다는 가정이 있습니다.'],
            'prediction_scope':'관측 장면 또는 세 아웃 전 한 점 상황의 저장된 흐름입니다.',
            'random_seed':result['seed'],'simulation_count':len(result['events']),
            'coverage':{'trace_events':len(result['events']),'probabilities_available':False,
                        'observed_state_fields':['outs','bases','runs']},
            'uncertainty':{'data_uncertainty_estimated':False,'model_uncertainty_estimated':False},
            'model_limitations':['개별 투구·스윙·9이닝 경기의 재현은 포함하지 않습니다.',
                                 '플레이 선택의 관측 편향은 이 장면만으로 해소되지 않습니다.']}
