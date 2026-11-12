"""Display adapter; the existing eight-category probability model is unchanged.

Retrosheet plays.html defines exactly one of single..noout per completed PA.
SH/SF/error/FC/interference are therefore mutually exclusive primary residuals.
GDP/DP and batted-ball flags only subdivide othout. FO can retire a preceding
runner while the batter survives: never call every othout a batter out.
Non-PA pitches/steals/fouls are not outcomes in this adapter.
"""
from collections import Counter,defaultdict
from pathlib import Path
from random import Random
import threading

from baseball_lab.data.catalog import DatasetCatalog
from baseball_lab.data.lineage import content_hash

VERSION='observed-residual-display-v1'
PRIMARY=('single','double','triple','hr','sh','sf','hbp','walk','k','xi','roe','fc','othout','noout')
KNOWN=('single','double','triple','hr','hbp','walk','k')
DETAIL_LABELS={'ground_out':'땅볼 아웃','fly_out':'뜬공 아웃','line_out':'직선타 아웃',
 'grounded_double_play':'병살타','double_play':'병살 플레이','triple_play':'삼중살 플레이',
 'runner_out':'선행주자 아웃','sacrifice_bunt':'희생번트','sacrifice_fly':'희생플라이',
 'reached_error':'실책 출루','fielders_choice':'야수선택','interference':'방해로 출루',
 'recorded_out':'아웃 플레이','unresolved':'그 밖의 결과'}
_CACHE={};_LOCK=threading.RLock()


def classify(row):
    if row.get('pa')!='1':return None
    values=[row.get(key) for key in PRIMARY]
    if any(value not in ('0','1') for value in values) or values.count('1')!=1:
        raise ValueError('타석 사건의 중복·결측으로 세부 분류를 만들지 않았습니다.')
    if not row.get('batter'):raise ValueError('타자 식별자가 없는 타석입니다.')
    if any(row[key]=='1' for key in KNOWN):return None
    for flag,name in (('sh','sacrifice_bunt'),('sf','sacrifice_fly'),('roe','reached_error'),
                      ('fc','fielders_choice'),('xi','interference')):
        if row[flag]=='1':return name
    if row['othout']=='1':
        for flag,name in (('gdp','grounded_double_play'),('tp','triple_play'),('othdp','double_play')):
            if row.get(flag)=='1':return name
        if '/FO' in row.get('event','') or row.get('batter') in [row.get(f'br{i}_post') for i in (1,2,3)]:
            return 'runner_out'
        for flag,name in (('ground','ground_out'),('fly','fly_out'),('line','line_out')):
            if row.get(flag)=='1':return name
        return 'recorded_out'
    return 'unresolved'


def index(root,year):
    registry=DatasetCatalog(root);metadata=registry.describe('match',year)
    if not metadata['ready']:raise ValueError('플레이별 기록이 없어 세부 사건을 구분하지 않았습니다.')
    signature=content_hash(metadata['metadata']['sha256']);key=(str(Path(root).resolve()),year,signature)
    with _LOCK:
        if key in _CACHE:return _CACHE[key]
    batters=defaultdict(Counter);pitchers=defaultdict(Counter);pairs=defaultdict(Counter)
    examples=defaultdict(list);dates={};seen=set();primary=Counter();pitch_codes=Counter()
    for row in registry.iter_plays(year):
        dates[row['gid']]=max(dates.get(row['gid'],''),row['date'])
        if row['pa']!='1':continue
        identity=(row['gid'],row['pn'])
        if identity in seen:raise ValueError('원본 타석 ID 중복')
        seen.add(identity);pitch_codes.update(row.get('pitches',''))
        detail=classify(row)
        primary[next(k for k in PRIMARY if row[k]=='1')]+=1
        if detail is None:continue
        batters[row['batter']][detail]+=1;pitchers[row['pitcher']][detail]+=1
        pairs[(row['batter'],row['pitcher'])][detail]+=1
        if len(examples[detail])<3:examples[detail].append({'game':row['gid'],'play':row['pn'],'event_code':row['event']})
    value={'batters':batters,'pitchers':pitchers,'pairs':pairs,'examples':dict(examples),
           'game_completion_dates':dates,'source_sha256':signature,'primary_counts':dict(primary),
           'pa_n':len(seen),'pitch_codes':dict(pitch_codes)}
    with _LOCK:_CACHE[key]=value
    return value


def attach(root,result):
    """Conditional empirical display split, never a replacement trained model."""
    events=result['simulation']['events'];display=list(events)
    definition='삼진·볼넷·사구·단타·2루타·3루타·홈런으로 분류되지 않은 타석입니다.'
    if result['model']['model']=='legacy':
        definition='원본 과제에서 삼진·볼넷·안타를 뺀 나머지입니다. 사구를 따로 계산하지 않는 원본 분기이며, 원인별 타석 기록이 없어 모두 타자 아웃이라고 단정할 수 없습니다.'
    explanation={'definition':definition,'detail_available':False,
                 'reason':'시즌 합계에는 타석별 아웃·실책·야수선택 기록이 없어 이 묶음을 더 나누지 않았습니다.',
                 'simulation_n':events.count('other'),'version':VERSION}
    if result['project']=='baseball':
        try:
            if result['batter']['season']!=result['pitcher'].get('season',result['batter']['season']):
                raise ValueError('서로 다른 시즌의 세부 잔여 사건은 임의로 혼합하지 않았습니다. 각 선수의 실제 기록은 해당 시즌으로 확인하세요.')
            data=index(root,result['batter']['season']);b=result['batter']['player_id'];p=result['pitcher']['player_id']
            a=data['batters'].get(b,Counter());z=data['pitchers'].get(p,Counter());overlap=data['pairs'].get((b,p),Counter())
            pool={key:a[key]+z[key]-overlap[key] for key in DETAIL_LABELS}
            n=sum(pool.values())
            if not n:raise ValueError('두 선수의 나머지 타석 표본이 없습니다.')
            rng=Random(int(content_hash({'run':result['run_id'],'display':VERSION})[:16],16))
            keys=[key for key,value in pool.items() if value];weights=[pool[key] for key in keys]
            for i,event in enumerate(events):
                if event=='other':display[i]=rng.choices(keys,weights=weights,k=1)[0]
            explanation.update(detail_available=True,reason=None,observed_pool_n=n,
                pool_definition='선택 타자의 타석 또는 선택 투수가 상대한 타석. 두 선수가 직접 만난 타석은 한 번만 셉니다.',
                observed_counts=pool,conditional_rates={key:value/n for key,value in pool.items()},
                source_sha256=data['source_sha256'],event_code_examples=data['examples'],
                scope='기존 모형의 나머지 확률 안에서 관측 비율로 세부 결과를 추정했습니다. 별도로 검증한 세부 확률 모형이나 실제 경기 재생은 아닙니다.')
        except ValueError as exc:explanation['reason']=str(exc)
    result['event_display']={'version':VERSION,'events':display,'labels':DETAIL_LABELS,
                             'other':explanation,'primary_model_unchanged':True}
    return result
