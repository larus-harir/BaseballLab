"""Adapt a matchup's event partition to observed field coverage, not league names.

Identity, exposure, strikeouts, walks and total hits are required. Known HBP,
2B, 3B and HR remain separate whenever both players and all reference populations
support them. Unknown fields remain unknown; only unresolved hits are grouped.
The four-event learning marginal in shared.partition is intentionally unchanged.
"""
from .models import generalized_log5

OPTIONAL={'HBP':'hbp','2B':'double','3B':'triple','HR':'home_run'}
LABELS={'strikeout':'삼진','walk':'볼넷','hbp':'사구','single':'단타','double':'2루타','triple':'3루타',
        'home_run':'홈런','hit_other':'그 외 안타','hit':'안타 (종류 미구분)','other':'그 밖의 결과'}
VERSION='adaptive-observed-events-relative-v2'


def partition(counts,role,fields):
    n=counts.get('PA' if role in ('batter','team_batting') else 'TBF')
    if type(n) is not int or n<=0 or any(type(counts.get(k)) is not int or counts[k]<0 for k in ('SO','BB','H',*fields)):
        raise ValueError('타석·상대 타자 수, 삼진·볼넷·안타의 실제 계수가 필요합니다.')
    result={'strikeout':counts['SO'],'walk':counts['BB']}
    if 'HBP' in fields:result['hbp']=counts['HBP']
    splits=[f for f in ('2B','3B','HR') if f in fields]
    hit_key='single' if len(splits)==3 else 'hit_other' if splits else 'hit'
    result[hit_key]=counts['H']-sum(counts[f] for f in splits)
    result.update({OPTIONAL[f]:counts[f] for f in splits})
    result['other']=n-counts['H']-counts['SO']-counts['BB']-(counts['HBP'] if 'HBP' in fields else 0)
    if any(v<0 for v in result.values()) or sum(result.values())!=n:raise ValueError('분리한 사건 합계와 실제 타석 분모가 모순됩니다.')
    return result


def model(data,batter,pitcher,target,strength):
    origins={role:f"{p['league']}:{p['season']}" for role,p in (('batter',batter),('pitcher',pitcher))}
    if any(k not in data['baselines'] for k in (*origins.values(),target)):raise ValueError('선수의 리그·시즌 기준 기록이 부족합니다.')
    populations={k:data['baselines'][k] for k in dict.fromkeys((*origins.values(),target))}
    counts={role:p['counts'] for role,p in (('batter',batter),('pitcher',pitcher))}
    counts.update({k:v['stat_counts'] for k,v in populations.items()})
    fields=[];missing={}
    for field in OPTIONAL:
        absent=[scope for scope,c in counts.items() if c.get(field) is None]
        if absent:missing[field]={'reason':'missing_source_field','scopes':absent}
        else:fields.append(field)
    player_counts={role:partition(p['counts'],role,fields) for role,p in (('batter',batter),('pitcher',pitcher))}
    baselines={}
    for key,original in populations.items():
        events=partition(original['stat_counts'],'batter',fields);n=sum(events.values())
        baselines[key]={**original,'counts':events,'rates':{k:v/n for k,v in events.items()},'sample_n':n}
    reference=baselines[target];ref=reference['rates'];keys=tuple(ref)
    labels={k:LABELS[k] for k in keys}
    if 'hit_other' in keys and set(fields)&{'2B','3B','HR'}=={'HR'}:labels['hit_other']='홈런 외 안타'
    steps={'reference':ref,'strength':strength,'target':target,'origins':{}}
    adjusted=[]
    for role in ('batter','pitcher'):
        observed=player_counts[role];n=sum(observed.values());prior=baselines[origins[role]]['rates']
        raw={k:v/n for k,v in observed.items()}
        shrunk={k:(observed[k]+strength*prior[k])/(n+strength) for k in keys}
        transported={}
        for k in keys:
            if prior[k]==0 and shrunk[k]>0:raise ValueError(labels[k]+'의 시즌 기준 표본이 없어 보정할 수 없습니다.')
            transported[k]=shrunk[k]*ref[k]/prior[k] if prior[k]>0 else 0.
        total=sum(transported.values())
        if not total:raise ValueError('기준 환경과 공통으로 관측된 사건이 없습니다.')
        value={k:v/total for k,v in transported.items()}
        steps.update({role+'_raw':raw,role+'_adjusted':value,role+'_n':n});steps['origins'][role]=baselines[origins[role]];adjusted.append(value)
    positive=[k for k in keys if ref[k]>0]
    q0,w0,total=generalized_log5(*({k:d[k] for k in positive} for d in adjusted),{k:ref[k] for k in positive})
    q={k:q0.get(k,0.) for k in keys};w={k:w0.get(k,0.) for k in keys}
    steps.update(weights=w,normalizer=total)
    policy={'required_identity_fields':['league','season','role','source_namespace','source_player_id','source_sha256'],
            'unknown_source_columns':'preserved in source_fields, excluded from calculations until their meaning is registered',
            'required_fields':{'batter':['PA','SO','BB','H'],'pitcher':['TBF','SO','BB','H']},
            'retained_optional_fields':fields,'unmodeled_fields':missing,
            'missing_fill':False,'basis':'Both players and every origin/target population must support each optional split.'}
    assumptions=['각 리그·시즌 평균 대비 상대 빈도를 선택한 환경으로 옮긴다는 가정입니다. 검증된 리그 실력 환산이 아닙니다.',
        '구장·상대·수비·규칙 효과는 별도 식별하지 못했습니다.',
        '확보한 홈런·장타·사구는 가능한 범위에서 분리하고, 미확인 안타 종류만 묶습니다. 없는 계수를 0이나 추정값으로 채우지 않습니다.',
        '시즌 합계는 전략 학습에 사용하지 않습니다.']
    return {'model':'common','version':VERSION,'probabilities':q,'steps':steps,'assumptions':assumptions,'field_policy':policy},labels,reference
