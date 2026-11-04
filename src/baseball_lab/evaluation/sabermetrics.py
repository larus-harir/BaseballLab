"""Descriptive batting metrics with explicit denominators and missing-data handling.

These are measurements, not ability estimates or training rewards. In particular,
OPS/SLG are not probabilities and a simulation's reach-base reward is not OBP.
"""
from dataclasses import asdict, dataclass

SOURCES={
    'BABIP':'https://www.mlb.com/glossary/advanced-stats/babip',
    'OBP':'https://www.mlb.com/glossary/standard-stats/on-base-percentage',
    'AVG':'https://www.mlb.com/glossary/standard-stats/batting-average',
    'SLG':'https://www.mlb.com/glossary/standard-stats/slugging-percentage',
    'OPS':'https://www.mlb.com/glossary/standard-stats/on-base-plus-slugging',
}


@dataclass(frozen=True)
class Metric:
    value: float | None
    numerator: int | None
    denominator: int | None
    reason: str | None
    definition: str
    source_url: str | None = None


def batting_metrics(counts: dict) -> dict[str, Metric]:
    keys={'PA','AB','H','2B','3B','HR','SO','BB','HBP','SF','SH'}
    if set(counts)-keys:raise ValueError('지표에 정의되지 않은 필드가 있습니다. HP 등은 원천 정의를 확인한 뒤 명시적으로 대응하세요.')
    for key,value in counts.items():
        if value is not None and (type(value) is not int or value<0):
            raise ValueError(f'{key}는 음이 아닌 정수 또는 결측이어야 합니다.')
    def known(*fields):return all(counts.get(field) is not None for field in fields)
    if known('H','AB') and counts['H']>counts['AB']:raise ValueError('안타가 타수보다 많습니다.')
    if known('H','SO','AB') and counts['H']+counts['SO']>counts['AB']:raise ValueError('안타와 삼진 합이 타수보다 많습니다.')
    if known('2B','3B','HR','H') and sum(counts[k] for k in ('2B','3B','HR'))>counts['H']:raise ValueError('장타 합이 안타 수보다 많습니다.')
    if counts.get('PA') is not None:
        if sum(counts.get(k) or 0 for k in ('AB','BB','HBP','SF','SH'))>counts['PA']:
            raise ValueError('타석 구성 항목의 합이 PA보다 큽니다. 분모·기간·중복을 확인하세요.')
    def ratio(name,needed,numerator,denominator,definition):
        if not known(*needed):
            return Metric(None,None,None,'필요한 기록 결측: '+', '.join(k for k in needed if counts.get(k) is None),definition,SOURCES.get(name))
        n,d=numerator(),denominator()
        if d<=0:return Metric(None,n,d,'분모가 0이라 계산할 수 없습니다.',definition,SOURCES.get(name))
        return Metric(n/d,n,d,None,definition,SOURCES.get(name))
    c=counts
    out={
        'AVG':ratio('AVG',('H','AB'),lambda:c['H'],lambda:c['AB'],'H / AB'),
        'OBP':ratio('OBP',('H','BB','HBP','AB','SF'),lambda:c['H']+c['BB']+c['HBP'],lambda:c['AB']+c['BB']+c['HBP']+c['SF'],'(H + BB + HBP) / (AB + BB + HBP + SF); 실책·선택수비 출루 제외'),
        'SLG':ratio('SLG',('H','2B','3B','HR','AB'),lambda:c['H']+c['2B']+2*c['3B']+3*c['HR'],lambda:c['AB'],'TB / AB; 확률이 아님'),
        'BABIP':ratio('BABIP',('H','HR','AB','SO','SF'),lambda:c['H']-c['HR'],lambda:c['AB']-c['SO']-c['HR']+c['SF'],'(H - HR) / (AB - SO - HR + SF)'),
        'K_RATE':ratio('K_RATE',('SO','PA'),lambda:c['SO'],lambda:c['PA'],'SO / PA'),
        'BB_RATE':ratio('BB_RATE',('BB','PA'),lambda:c['BB'],lambda:c['PA'],'BB / PA; IBB 포함 여부는 원천 BB 정의 확인'),
    }
    obp,slg=out['OBP'],out['SLG']
    out['OPS']=Metric(obp.value+slg.value if obp.value is not None and slg.value is not None else None,
                      None,None,None if obp.value is not None and slg.value is not None else 'OBP 또는 SLG를 계산할 수 없습니다.',
                      'OBP + SLG; 확률이 아님',SOURCES['OPS'])
    return out


def validate_probability_distribution(probabilities):
    """Reject invalid competing outcomes instead of silently clipping their remainder."""
    import math
    if not probabilities or any(type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1 for p in probabilities.values()):
        raise ValueError('각 사건 확률은 유한한 0~1 값이어야 합니다.')
    if not math.isclose(sum(probabilities.values()),1.,abs_tol=1e-10):
        raise ValueError('배타적인 사건들의 확률 합이 1이 아닙니다. 각 확률을 따로 보정해 만든 합은 유효한 결합 분포가 아닐 수 있습니다.')
