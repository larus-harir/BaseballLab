"""Shared, explicit outcome models. No strategy learning or physical simulation."""
import math
from random import Random
from baseball_lab.evaluation.sabermetrics import validate_probability_distribution
from baseball_lab.simulation.contracts import EVENTS

LABELS=dict(zip(EVENTS,('삼진','볼넷','사구','단타','2루타','3루타','홈런','그 밖의 결과')))
MODEL_VERSION='categorical-log5-v1'
LEGACY_CONSTANTS={'batter_k':150,'batter_bb':200,'batter_hr':300,'batter_babip':800,'p_k':150,'p_bb':200,'p_hr':400}


def log5(b,p,l):
    if not all(math.isfinite(x) and 0<x<1 for x in (b,p,l)):raise ValueError('이항 Log5의 비율은 0과 1 사이여야 합니다.')
    a=b*p/l;return a/(a+(1-b)*(1-p)/(1-l))


def distribution(counts):
    if set(counts)!=set(EVENTS) or any(type(n) is not int or n<0 for n in counts.values()) or sum(counts.values())<=0:
        raise ValueError('누락 없는 배타적 사건 수와 양의 타석 분모가 필요합니다.')
    return {k:counts[k]/sum(counts.values()) for k in EVENTS}


def stabilize(counts,league,strength):
    if not math.isfinite(strength) or strength<0:raise ValueError('보정 강도는 음수가 될 수 없습니다.')
    if set(counts)!=set(EVENTS) or any(type(n) is not int or n<0 for n in counts.values()):raise ValueError('잘못된 사건 수')
    n=sum(counts.values())
    if not n:return dict(league)  # Explicit cold-start prior, used only in held-out evaluation.
    return {k:(counts[k]+strength*league[k])/(n+strength) for k in EVENTS}


def generalized_log5(b,p,league):
    keys=tuple(b)
    if not keys or set(p)!=set(keys) or set(league)!=set(keys):raise ValueError('세 분포의 사건 정의가 같아야 합니다.')
    for v in (b,p,league):validate_probability_distribution(v)
    if any(league[k]<=0 for k in keys):raise ValueError('리그에 관측되지 않은 사건은 임의 확률로 채우지 않습니다.')
    weights={k:b[k]*p[k]/league[k] for k in keys};total=sum(weights.values())
    if not total:raise ValueError('두 프로필의 공통 사건 확률이 없습니다. 표본 보정 또는 자료 검토가 필요합니다.')
    result={k:weights[k]/total for k in keys};validate_probability_distribution(result)
    return result,weights,total


def normalized(batter,pitcher,league,*,strength=100,neutral=None):
    if type(strength) not in (int,float) or not math.isfinite(strength) or strength<0:raise ValueError('표본 보정 강도를 확인하세요.')
    b0=distribution(batter['events']);p0=distribution(pitcher['events'])
    reference=neutral or league
    # Cross-season relative-rate transport is an assumption, then normalized
    # over the complete event partition. No clipping or hidden missing outcomes.
    def transport(raw,origin):
        if any(origin[k]<=0 for k in EVENTS):raise ValueError('시즌 기준의 사건 표본이 부족합니다.')
        w={k:raw[k]*reference[k]/origin[k] for k in EVENTS};t=sum(w.values());return {k:w[k]/t for k in EVENTS}
    b_era=transport(b0,batter.get('league_rates',league));p_era=transport(p0,pitcher.get('league_rates',league))
    n_b=sum(batter['events'].values());n_p=sum(pitcher['events'].values())
    b={k:(b_era[k]*n_b+strength*reference[k])/(n_b+strength) for k in EVENTS}
    p={k:(p_era[k]*n_p+strength*reference[k])/(n_p+strength) for k in EVENTS}
    q,w,total=generalized_log5(b,p,reference)
    return {'model':'normalized','version':MODEL_VERSION,'probabilities':q,
            'steps':{'batter_raw':b0,'pitcher_raw':p0,'batter_era':b_era,'pitcher_era':p_era,
                     'batter_adjusted':b,'pitcher_adjusted':p,'reference':reference,'weights':w,'normalizer':total,
                     'strength':strength,'batter_n':n_b,'pitcher_n':n_p},
            'assumptions':['사건별 상대 빈도 결합은 미관측 맞대결의 인과효과를 식별하지 않습니다.',
                           '표본 보정은 불확실성을 줄이기 위한 추정이며 순수 실력이나 운 제거의 증명이 아닙니다.']}


def legacy(batter,pitcher,yearly,all_rates):
    """Equations and ordered thresholds of the supplied assignment, not its claims."""
    b,p=batter['legacy_row'],pitcher['legacy_row'];l=all_rates;by=yearly[str(batter['season'])];py=yearly[str(pitcher['season'])]
    if any(b.get(k) is None for k in ('PA','AB','H','SO','BB','HR','2B','3B')) or any(p.get(k) is None for k in ('TBF','SO','BB','HR')):raise ValueError('과제 재현의 필수 기록이 결측입니다.')
    if any(rate<=0 for rates in (l,by,py) for rate in rates.values()):raise ValueError('과제 시대 보정의 리그 분모가 0입니다.')
    b={**b,'SF':b.get('SF') or 0}  # Original explicitly treats missing SF as zero.
    n,m=b['PA'],p['TBF'];bip=b['AB']-b['SO']-b['HR']+b['SF']
    if n<=0 or m<=0:raise ValueError('과제 재현에 필요한 PA/TBF가 없습니다.')
    braw={'K_rate':b['SO']/n,'BB_rate':b['BB']/n,'HR_rate':b['HR']/n,'BABIP':(b['H']-b['HR'])/max(bip,1)}
    praw={'K_rate':p['SO']/m,'BB_rate':p['BB']/m,'HR_rate':p['HR']/m}
    bn={k:v*l[k]/by[k] for k,v in braw.items()};pn={k:v*l[k]/py[k] for k,v in praw.items()}
    def regress(raw,sample,k):return (raw*sample+LEGACY_CONSTANTS[k]*l[{'k':'K_rate','bb':'BB_rate','hr':'HR_rate','babip':'BABIP'}[k.split('_',1)[1]]])/(sample+LEGACY_CONSTANTS[k])
    bt={key:regress(bn[key],bip if key=='BABIP' else n,'batter_'+suffix) for key,suffix in [('K_rate','k'),('BB_rate','bb'),('HR_rate','hr'),('BABIP','babip')]}
    pt={key:regress(pn[key],m,'p_'+suffix) for key,suffix in [('K_rate','k'),('BB_rate','bb'),('HR_rate','hr')]};pt['BABIP']=l['BABIP']
    def original_log(a,b,c):return log5(*(max(.001,min(.999,x)) for x in (a,b,c)))
    claimed={k:original_log(bt[k],pt[k],l[k]) for k in bt}
    k,bb,hr=claimed['K_rate'],claimed['BB_rate'],claimed['HR_rate'];in_hit=max(0,1-k-bb-hr)*claimed['BABIP']
    den=max(b['H']-b['HR'],1);single=(b['H']-b['2B']-b['3B']-b['HR'])/den;double=b['2B']/den
    if single<0 or double<0 or single+double>1+1e-12:raise ValueError('과제 원본의 안타 구성 비율이 모순입니다.')
    # Preserve the original threshold branch behavior, even when its displayed
    # K+BB+HR exceed 1. Effective intervals are shown explicitly, not hidden.
    bounds=[min(1,x) for x in (0,k,k+bb,k+bb+hr,k+bb+hr+in_hit)]
    hit=bounds[4]-bounds[3]
    single_end=min(1.,single);double_end=min(1.,single+double)
    q=dict(zip(EVENTS,(bounds[1],bounds[2]-bounds[1],0.,hit*single_end,hit*(double_end-single_end),hit*(1-double_end),bounds[3]-bounds[2],1-bounds[4])))
    validate_probability_distribution(q)
    return {'model':'legacy','version':'assignment-original-v1','probabilities':q,
            'legacy_sampling':{'k':k,'bb':bb,'hr':hr,'in_hit':in_hit,'single':single,'double':double},
            'steps':{'batter_raw':braw,'pitcher_raw':praw,'batter_era':bn,'pitcher_era':pn,'batter_adjusted':bt,
                     'pitcher_adjusted':pt,'reference':l,'claimed_binary':claimed,'displayed_k_bb_hr_sum':k+bb+hr,
                     'constants':LEGACY_CONSTANTS,'batter_n':n,'pitcher_n':m},
            'assumptions':['과제 방식 재현(연구 검증 전). 원본은 사구를 별도 사건으로 사용하지 않습니다.',
                           '투수 BABIP를 리그 평균으로 고정하는 원본 가정입니다. 현실 법칙이 아닙니다.',
                           '리그 통산 대비 비율 보정과 고정 안정화 상수는 원본 의도 재현이며 검증된 시대 중립화가 아닙니다.',
                           '표시한 개별 이항 확률과 실제 순서 분기의 실현 확률이 다를 수 있어 둘 다 공개합니다.']}


def simulate(model,n=25,seed=41,repetitions=200):
    if type(n) is not int or not 1<=n<=10000 or type(repetitions) is not int or not 1<=repetitions<=200 or n*repetitions>2000000:raise ValueError('대결은 1~10,000타석, 반복은 1~200회입니다.')
    if type(seed) is not int or not 0<=seed<=2**31-1:raise ValueError('재현 번호를 확인하세요.')
    q=model['probabilities'];validate_probability_distribution(q)
    keys=tuple(q)
    def draw(rng):
        u=rng.random()
        if model['model']=='legacy':
            x=model['legacy_sampling'];k,bb,hr=x['k'],x['bb'],x['hr']
            if u<k:return 'strikeout'
            if u<k+bb:return 'walk'
            if u<k+bb+hr:return 'home_run'
            if u<k+bb+hr+x['in_hit']:
                h=rng.random();return 'single' if h<x['single'] else 'double' if h<x['single']+x['double'] else 'triple'
            return 'other'
        cumulative=0.
        for event in keys:
            cumulative+=q[event]
            if u<cumulative:return event
        return keys[-1]  # Floating rounding only, not discarded event mass.
    rng=Random(seed);events=[draw(rng) for _ in range(n)];counts={e:events.count(e) for e in keys}
    experiments=[]
    for repeat in range(repetitions):
        r=Random(seed+100000+repeat);c={e:0 for e in keys}
        for _ in range(n):c[draw(r)]+=1
        experiments.append(c)
    bands={}
    for e in keys:
        values=sorted(c[e] for c in experiments)
        bands[e]={'mean':sum(values)/len(values),'range_95':[values[int((len(values)-1)*.025)],values[int((len(values)-1)*.975)]]}
    return {'n':n,'seed':seed,'repetitions':repetitions,'events':events,'counts':counts,
            'expected':{e:n*q[e] for e in keys},'sampling_bands':bands,
            'uncertainty':'반복 범위는 계산된 확률을 고정한 난수 변동만 보여줍니다. 자료·모델 불확실성은 포함하지 않습니다.'}
