"""Definitions are knowledge metadata, not extra inputs secretly taught to an AI.

Advanced provider-specific metrics intentionally have no invented coefficients.
Known denominators are described even when the active models do not use a metric.
"""
from copy import deepcopy

MLB = 'https://www.mlb.com/glossary/'


def _entry(name, definition, formula, numerator, denominator, unit, fields,
           source, cautions, used_by=(), availability='필요한 원천 필드가 모두 있는 시즌/선수에만 계산 가능'):
    return {'id': name, 'name': name, 'definition': definition, 'formula': formula,
            'numerator': numerator, 'denominator': denominator, 'unit': unit,
            'required_fields': fields, 'availability': availability,
            'source_url': source, 'cautions': cautions, 'used_by': list(used_by),
            'used_in_active_probability_model': bool(used_by)}


_REGISTRY = [
    _entry('AVG', '타수 중 안타 비율', 'H / AB', 'H', 'AB', '비율', ['H', 'AB'],
           MLB+'standard-stats/batting-average', ['AB는 PA−BB와 일반적으로 같지 않으며 사구·희생타 등의 타석을 구분해야 합니다.']),
    _entry('OBP', '안타·볼넷·사구에 의한 출루 비율', '(H + BB + HBP) / (AB + BB + HBP + SF)',
           'H + BB + HBP', 'AB + BB + HBP + SF', '비율', ['H', 'BB', 'HBP', 'AB', 'SF'],
           MLB+'standard-stats/on-base-percentage', ['실책·선택수비 출루는 분자에 넣지 않습니다.', 'HP를 HBP로 대응하려면 원천 정의 확인이 필요합니다.']),
    _entry('SLG', '타수당 총 루타', '(H + 2B + 2×3B + 3×HR) / AB', 'TB', 'AB', '루타/타수', ['H', '2B', '3B', 'HR', 'AB'],
           MLB+'standard-stats/slugging-percentage', ['확률이 아닙니다. 1을 넘을 수 있으며 결과 사건의 분포로 사용할 수 없습니다.']),
    _entry('OPS', '출루율과 장타율의 합', 'OBP + SLG', None, None, '지수', ['OBP', 'SLG'],
           MLB+'standard-stats/on-base-plus-slugging', ['두 항의 분모가 다릅니다. 확률 또는 특정 사건의 기대 개수가 아닙니다.']),
    _entry('BABIP', '홈런을 제외하고 인플레이가 된 타구 중 안타 비율', '(H − HR) / (AB − SO − HR + SF)',
           'H − HR', 'AB − SO − HR + SF', '비율', ['H', 'HR', 'AB', 'SO', 'SF'],
           MLB+'advanced-stats/babip', ['SF 결측을 개선 모델에서 임의 0으로 채우지 않습니다.', '타구 질·수비·구장·표본 변동이 함께 들어 있습니다. 운만 또는 순수 실력만 나타내지 않습니다.', '과제 재현에서 투수 BABIP의 리그 평균 고정은 원본 가정이며 현실 법칙이 아닙니다.'],
           ['assignment-original-v1']),
    _entry('K%', '타석 또는 상대 타자 중 삼진 비율', 'SO / PA (타자); SO / TBF (투수)', 'SO', 'PA 또는 TBF', '비율', ['SO', 'PA_or_TBF'],
           MLB+'advanced-stats/strikeout-rate', ['투수 K/9과 분모가 다릅니다.', '0~1 비율을 저장하며 화면의 백분율은 100을 곱합니다.'],
           ['assignment-original-v1', 'categorical-log5-v1']),
    _entry('BB%', '타석 또는 상대 타자 중 볼넷 비율', 'BB / PA (타자); BB / TBF (투수)', 'BB', 'PA 또는 TBF', '비율', ['BB', 'PA_or_TBF'],
           MLB+'advanced-stats/walk-rate', ['BB/IB의 포함 관계는 원천 정의에 따릅니다.', '사구와 볼넷을 합쳐 출루율로 부르지 않습니다.'],
           ['assignment-original-v1', 'categorical-log5-v1']),
    _entry('K/9', '9이닝당 삼진', '27 × SO / IP_OUTS', '27 × SO', 'IP_OUTS', '삼진/9이닝', ['SO', 'IP_OUTS'],
           MLB+'advanced-stats/strikeouts-per-nine-innings', ['야구의 123.2이닝은 123.2 실수 이닝이 아니라 371아웃입니다.', 'K%와 서로 대체할 수 없습니다.']),
    _entry('BB/9', '9이닝당 볼넷', '27 × BB / IP_OUTS', '27 × BB', 'IP_OUTS', '볼넷/9이닝', ['BB', 'IP_OUTS'],
           MLB+'advanced-stats/walks-per-nine-innings', ['IBB 포함 여부는 원천 정의 확인이 필요합니다.', '9이닝의 분모를 PA/TBF와 혼동하지 않습니다.']),
    _entry('FIP', '삼진·볼넷·사구·홈런과 이닝으로 구성하는 투수 지표', '(13×HR + 3×(BB+HBP) − 2×SO) / IP + cFIP',
           '13×HR + 3×(BB+HBP) − 2×SO', 'IP (IP_OUTS/3)', 'ERA 척도 지수', ['HR', 'BB', 'HBP', 'SO', 'IP_OUTS', 'cFIP'],
           MLB+'advanced-stats/fielding-independent-pitching', ['cFIP는 해당 리그·시즌·공급원의 정렬 상수입니다. 임의 상수를 고정하지 않습니다.', '인플레이를 제외한 지표 설계이지 투수가 인플레이 타구에 전혀 영향이 없다는 증명은 아닙니다.']),
    _entry('wOBA', '득점 가치 가중치를 이용한 출루 사건의 종합 비율', '시즌별 사건 가중합 / 해당 공급원이 정의한 타격 기회 분모',
           '시즌별 wBB×uBB + wHBP×HBP + w1B×1B + w2B×2B + w3B×3B + wHR×HR',
           '보통 AB + BB − IBB + SF + HBP; 공급원 정의 확인', '가중 비율', ['AB', 'BB', 'IBB', 'HBP', 'SF', '1B', '2B', '3B', 'HR', 'season_weights'],
           MLB+'advanced-stats/weighted-on-base-average', ['시즌별 선형 가중치·스케일을 임의로 생성하지 않습니다.', '모든 안타를 같은 가치로 세지 않지만 완전한 상황별 전술 효과는 아닙니다.']),
    _entry('wRC+', '리그·구장 등을 조정한 타격 득점 생산의 상대 지수', '공급원별 wRC/리그/구장 보정; 평균 100',
           None, None, '리그 평균 100의 지수', ['wRAA_or_wRC', 'PA', 'league_runs', 'park_factor', 'provider_method'],
           MLB+'advanced-stats/weighted-runs-created-plus', ['공급원·구장·시대 보정 구현이 필요합니다.', '과제 CSV의 값을 읽었다고 이 지표를 모델 입력으로 사용한 것은 아닙니다.']),
    _entry('WAR', '대체 수준 선수 대비 기여를 승수 척도로 합산한 추정치', '공급원별 타격·주루·수비·포지션·대체수준·투구 모델의 합성',
           None, None, '대체 수준 대비 승수', ['provider_component_models', 'replacement_level', 'runs_per_win'],
           MLB+'advanced-stats/wins-above-replacement', ['단일 보편 공식이 아니며 공급원끼리 정의가 다릅니다.', '승률·실제 팀 승수·인과적 기여를 직접 측정한 값이 아닙니다.']),
    _entry('DIPS', '인플레이 타구와 구분해 투수를 평가하려는 연구 관점', '단일 고정 산식 없음', None, None, '개념', [],
           MLB+'advanced-stats/fielding-independent-pitching', ['DIPS와 FIP는 동일한 이름의 확률 모델이 아닙니다.', '투수 BABIP를 영구히 같은 값으로 두라는 현실 법칙으로 취급하지 않습니다.']),
    _entry('Log5', '타자·투수·리그 상대 빈도를 결합하는 사건 확률 추정',
           '이항: (b×p/l) / (b×p/l + (1−b)×(1−p)/(1−l)); 다항: qᵢ = (bᵢ×pᵢ/lᵢ) / Σⱼ(bⱼ×pⱼ/lⱼ)',
           '타자·투수 상대 사건 가중치', '전체 경쟁 사건 가중치 합', '확률 분포', ['batter_event_rates', 'pitcher_event_rates', 'league_event_rates'],
           'https://sabr.org/journal/article/matchup-probabilities-in-major-league-baseball/',
           ['이항 사건을 따로 결합하면 전체 합 1이 보장되지 않습니다.', '희소 표본·상대 선택·구장·플래툰 등의 누락을 독립 검증해야 합니다.', '통계적 맞대결 추정은 미관측 행동의 인과효과나 9이닝 물리 시뮬레이션이 아닙니다.'],
           ['assignment-original-v1', 'categorical-log5-v1']),
]


def get_knowledge(metric_id=None):
    """Return independent JSON-ready values so a UI cannot mutate definitions."""
    if metric_id is None:
        return {'schema': 'sabermetric-knowledge-v1', 'metrics': deepcopy(_REGISTRY),
                'scope': 'Definitions and denominators only; metadata does not mean all these metrics are model inputs or available for every season.'}
    if not isinstance(metric_id, str):
        raise ValueError('지표 이름이 필요합니다.')
    for entry in _REGISTRY:
        if entry['id'].casefold() == metric_id.casefold():
            return deepcopy(entry)
    raise ValueError('등록된 지표가 아닙니다.')
