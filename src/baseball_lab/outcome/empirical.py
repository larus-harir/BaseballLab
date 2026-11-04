"""Observed-action frequency model. No intended location or invented ability effects."""
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from baseball_lab.data.lineage import content_hash, utc_now, write_json
from baseball_lab.data.statcast import load_dataset
from baseball_lab.evaluation.metrics import wilson_interval

EVENTS = ('ball','strike','foul','out','single','double','triple','home_run','reached')
MODEL_VERSION = 'statcast-observational-pa-v2'
ASSUMPTIONS = [
    'UNVERIFIED_ASSUMPTION: observed-action conditioning is associational, not an identified causal intervention',
    'UNVERIFIED_ASSUMPTION: pooled players/situations and pitch selection are exchangeable within fitted groups',
    'UNVERIFIED_ASSUMPTION: hierarchical pooling can remove pitch-type/location/count effects in sparse cells',
    'Pitch arrival is sampled independently of the chosen batter action; outcomes condition on its observed zone bin',
    'Unsupported: intended location, power/contact intention, bunt, fatigue, player abilities, full-game baserunning',
]


def region(row):
    x,z,top,bottom=(row.get(k) for k in ('plate_x','plate_z','sz_top','sz_bot'))
    if any(v is None for v in (x,z,top,bottom)):
        return 'missing_location'
    return 'geometric_inside' if abs(x)<=17/24 and bottom<=z<=top else 'geometric_outside'


class EmpiricalModel:
    def __init__(self, artifact):
        self.artifact = artifact
        self.records = artifact['fit_records']
        self.min_support = artifact['settings']['min_support']
        self.pitch_types = tuple(artifact['pitch_types'])
        self.groups = defaultdict(list)
        self.arrivals = defaultdict(list)
        for row in self.records:
            b,s,a,k = row['balls'],row['strikes'],row['observed_action'],row['pitch_type']
            self.groups[(b,s,a,k)].append(row)
            self.groups[(b,s,a,None)].append(row)
            self.groups[(b,s,a,k,region(row))].append(row)
            self.groups[(b,s,a,None,region(row))].append(row)
            self.arrivals[(b,s,k)].append(row)
            self.arrivals[(None,None,k)].append(row)

    def donors(self, balls, strikes, pitch_type, action, arrival=None):
        if pitch_type not in self.pitch_types or action not in ('take','swing'):
            raise ValueError('데이터로 지원하지 않는 행동')
        if arrival is not None:
            for key,level in (((balls,strikes,action,pitch_type,region(arrival)), 'count/action/pitch_type/observed_region'),
                              ((balls,strikes,action,None,region(arrival)), 'count/action/observed_region (pitch type pooled)')):
                if len(self.groups[key]) >= self.min_support:
                    return self.groups[key], level
        fine = (balls,strikes,action,pitch_type)
        if len(self.groups[fine]) >= self.min_support:
            return self.groups[fine], 'count/action/pitch_type'
        pooled = self.groups[(balls,strikes,action,None)]
        if len(pooled) < self.min_support:
            raise ValueError(f'자료 부족: {balls}-{strikes}, {action}, {pitch_type}')
        return pooled, 'count/action (pitch type pooled)'

    def probabilities(self, balls, strikes, pitch_type, action, arrival=None):
        donors, level = self.donors(balls,strikes,pitch_type,action,arrival)
        counts = Counter(row['event'] for row in donors)
        return {event:counts[event]/len(donors) for event in EVENTS}, len(donors), level

    def arrival_donors(self, balls, strikes, pitch_type):
        fine=self.arrivals[(balls,strikes,pitch_type)]
        if len(fine)>=self.min_support:
            return fine,'count/pitch_type'
        pooled=self.arrivals[(None,None,pitch_type)]
        if len(pooled)<self.min_support:
            raise ValueError('투구 도착 분포 표본 부족')
        return pooled,'pitch_type (count pooled)'

    def sample(self, balls, strikes, pitch_type, action, rng):
        arrivals,arrival_level=self.arrival_donors(balls,strikes,pitch_type)
        arrival=rng.choice(arrivals)  # Never condition this physical draw on batter action.
        donors, level = self.donors(balls,strikes,pitch_type,action,arrival)
        row = rng.choice(donors)
        probabilities, n, _ = self.probabilities(balls,strikes,pitch_type,action,arrival)
        return {'event':row['event'],'sampled_record':arrival,'probabilities':probabilities,
                'support_n':n,'backoff_level':level,'source_status':'MOCK_TEST_ONLY' if self.artifact['source_status']=='MOCK_TEST_ONLY' else 'MODEL_SIMULATED',
                'arrival_support_n':len(arrivals),'arrival_backoff_level':arrival_level,
                'probability_status':'EMPIRICALLY_ESTIMATED', 'model_version':MODEL_VERSION,
                'probability_intervals':{event:wilson_interval(round(p*n),n) for event,p in probabilities.items()},
                'reference_record_ids':list(dict.fromkeys([arrival['record_id'],row['record_id']]))}


def validate(model, rows, seed):
    from random import Random
    rng=Random(seed)
    observed,expected,simulated=Counter(),Counter(),Counter()
    groups=defaultdict(lambda:{'n':0,'observed':Counter(),'expected':Counter()})
    arrival_stats=defaultdict(lambda:defaultdict(list))
    supported = unseen = 0
    nll = brier = baseline_brier = 0.
    for row in rows:
        try:
            probs,n,level=model.probabilities(row['balls'],row['strikes'],row['pitch_type'],row['observed_action'],row)
        except ValueError:
            continue
        supported += 1
        arrival_rows,_=model.arrival_donors(row['balls'],row['strikes'],row['pitch_type'])
        for field in ('plate_x','plate_z','release_speed_kmh'):
            actual=row.get(field)
            fitted=[r[field] for r in arrival_rows if r.get(field) is not None]
            if actual is not None and fitted:
                arrival_stats[(row['pitch_type'],field)]['observed'].append(actual)
                arrival_stats[(row['pitch_type'],field)]['expected'].append(sum(fitted)/len(fitted))
        observed[row['event']] += 1
        for event,p in probs.items(): expected[event] += p
        donors,_=model.donors(row['balls'],row['strikes'],row['pitch_type'],row['observed_action'],row)
        simulated[rng.choice(donors)['event']] += 1
        p=probs[row['event']]
        unseen += p == 0
        nll -= math.log(max(p,1e-12))
        brier += sum((probs[event]-(row['event']==event))**2 for event in EVENTS)
        baseline_rows=model.groups[(row['balls'],row['strikes'],row['observed_action'],None)]
        baseline_counts=Counter(r['event'] for r in baseline_rows)
        baseline_brier += sum((baseline_counts[event]/len(baseline_rows)-(row['event']==event))**2 for event in EVENTS)
        key=f"{row['pitch_type']}:{row['balls']}-{row['strikes']}:{row['observed_action']}"
        group=groups[key];group['n']+=1;group['observed'][row['event']]+=1
        for event,p in probs.items(): group['expected'][event]+=p
    distributions=[]
    for event in EVENTS:
        real=observed[event]/supported if supported else None
        predicted=expected[event]/supported if supported else None
        sampled=simulated[event]/supported if supported else None
        distributions.append({'event':event,'n':observed[event],'observed':real,'predicted':predicted,'simulated':sampled,
                              'absolute_error':abs(real-predicted) if supported else None})
    conditions=[]
    for key,group in sorted(groups.items()):
        n=group['n']
        error=sum(abs(group['observed'][e]/n-group['expected'][e]/n) for e in EVENTS)/2
        conditions.append({'condition':key,'n':n,'total_variation':error,'small_sample':n<30})
    return {'n':len(rows),'supported_n':supported,'unsupported_n':len(rows)-supported,
            'coverage':supported/len(rows) if rows else 0,'unseen_event_n':unseen,
            'nll_epsilon_1e_12':nll/supported if supported else None,
            'brier':brier/supported if supported else None,
            'count_action_baseline_brier':baseline_brier/supported if supported else None,
            'brier_difference_vs_baseline':(brier-baseline_brier)/supported if supported else None,
            'weighted_conditional_tv':sum(c['n']*c['total_variation'] for c in conditions)/supported if supported else None,
            'total_variation':sum(d['absolute_error'] for d in distributions)/2 if supported else None,
            'distributions':distributions,'conditions':conditions,'simulation_seed':seed,
            'arrival_validation':[{'pitch_type':key[0],'field':key[1],'n':len(values['observed']),
               'observed_mean':sum(values['observed'])/len(values['observed']),
               'estimated_mean':sum(values['expected'])/len(values['expected']),
               'absolute_mean_error':abs(sum(values['observed'])-sum(values['expected']))/len(values['observed'])}
               for key,values in sorted(arrival_stats.items())],
            'source_statuses':{'observed':'REAL_OBSERVED','predicted':'EMPIRICALLY_ESTIMATED','simulated':'MODEL_SIMULATED'}}


def fit(dataset_path: Path, output: Path, *, train_before: str, test_from: str,
        min_support: int = 10, min_fit_rows: int = 500, min_holdout_rows: int = 100, test_only: bool = False):
    if type(min_support) is not int or min_support < 1:
        raise ValueError('min_support must be a positive integer')
    if date.fromisoformat(train_before) >= date.fromisoformat(test_from):
        raise ValueError('훈련/검증/최종검증 기간 경계를 순서대로 지정하세요.')
    dataset=load_dataset(dataset_path)
    manifest,records=dataset['manifest'],dataset['records']
    if manifest['source_status']!='REAL_OBSERVED' and not (test_only and manifest['source_status']=='MOCK_TEST_ONLY'):
        raise ValueError('실제 기록으로 확인되지 않은 자료로 연구용 보정을 할 수 없습니다.')
    if test_only and manifest['source_status']!='MOCK_TEST_ONLY':
        raise ValueError('test_only는 테스트 전용 자료에서만 사용하세요.')
    partitions={name:[] for name in ('fit','validation','test')}
    for row in records:
        key='fit' if row['game_date']<train_before else 'validation' if row['game_date']<test_from else 'test'
        partitions[key].append(row)
    game_sets={k:{r['game_pk'] for r in rows} for k,rows in partitions.items()}
    if any(game_sets[a]&game_sets[b] for a,b in (('fit','validation'),('fit','test'),('validation','test'))):
        raise ValueError('경기 ID가 데이터 분할을 가로질러 정보 누수가 발생합니다.')
    fit_rows=partitions['fit']
    if not fit_rows or not partitions['validation'] or not partitions['test']:
        raise ValueError('훈련·검증·최종 검증 기간에 각각 자료가 필요합니다.')
    settings={'min_support':min_support,'min_fit_rows':min_fit_rows,'min_holdout_rows':min_holdout_rows,
              'minimum_holdout_coverage':.95,'maximum_validation_tv':.15, 'maximum_weighted_conditional_tv':.30,'maximum_brier_increase_vs_baseline':.02,
              'note':'Predeclared engineering eligibility thresholds, not proof of causal/physical realism'}
    types=sorted(k for k,n in Counter(r['pitch_type'] for r in fit_rows).items() if n>=min_support)
    artifact={'model_version':MODEL_VERSION,'source_status':'EMPIRICALLY_ESTIMATED' if not test_only else 'MOCK_TEST_ONLY',
              'dataset_path':str(Path(dataset_path).resolve()),'dataset_version':manifest['dataset_version'],
              'fit_records':fit_rows,'pitch_types':types,'settings':settings,'assumptions':ASSUMPTIONS,
              'split':{k:{'n':len(rows),'game_ids':sorted(game_sets[k]),'record_ids':[r['record_id'] for r in rows],
                          'date_range':[min(r['game_date'] for r in rows),max(r['game_date'] for r in rows)]} for k,rows in partitions.items()},
              'train_before':train_before,'test_from':test_from,'created_at':utc_now()}
    model=EmpiricalModel(artifact)
    validation=validate(model,partitions['validation'],271828)
    test=validate(model,partitions['test'],314159)
    if test_only:
        for metrics in (validation,test):
            metrics['source_statuses']={key:'MOCK_TEST_ONLY' for key in metrics['source_statuses']}
    issues=[]
    if len(fit_rows)<min_fit_rows: issues.append('insufficient fit rows')
    if any(len(partitions[k])<min_holdout_rows for k in ('validation','test')): issues.append('insufficient holdout rows')
    if not types: issues.append('no supported pitch type')
    if manifest['count_sequence_mismatches']: issues.append('count-sequence inconsistencies')
    if manifest['exclusions'].get('invalid_key_count_or_numeric',0): issues.append('invalid required data rows')
    for balls in range(4):
        for strikes in range(3):
            for action in ('take','swing'):
                if len(model.groups[(balls,strikes,action,None)])<min_support:
                    issues.append(f'unsupported state {balls}-{strikes} {action}')
    if min(validation['coverage'],test['coverage'])<.95: issues.append('holdout support below threshold')
    if validation['total_variation'] is None or validation['total_variation']>.15: issues.append('validation distribution error above threshold')
    if validation['weighted_conditional_tv'] is None or validation['weighted_conditional_tv']>.30:
        issues.append('conditional errors too high even if aggregate frequencies match')
    if validation['brier_difference_vs_baseline'] is None or validation['brier_difference_vs_baseline']>.02:
        issues.append('model worse than count/action baseline')
    artifact['validation']={'validation':validation,'test':test,
                            'eligibility_issues':issues, 'research_ready':not issues and manifest['source_status']=='REAL_OBSERVED',
                            'status':'LIMITED_OBSERVATIONAL_POC' if not issues and not test_only else 'MOCK_TEST_ONLY' if test_only else 'VALIDATION_FAILED',
                            'causal_validity':'UNVERIFIED_ASSUMPTION'}
    artifact['model_id']=content_hash({k:v for k,v in artifact.items() if k not in ('created_at','dataset_path')})
    output=Path(output)
    write_json(output/'model.json',artifact)
    write_json(output/'validation.json',artifact['validation'])
    return artifact


def load_model(path, *, test_only=False):
    artifact=json.loads(Path(path).read_text(encoding='utf-8'))
    if artifact['model_version']!=MODEL_VERSION:
        raise ValueError('모델 버전 불일치')
    digest=content_hash({k:v for k,v in artifact.items() if k not in ('created_at','dataset_path','model_id')})
    if digest!=artifact['model_id']:
        raise ValueError('모델 파일 무결성 불일치')
    dataset=load_dataset(artifact['dataset_path'])
    if dataset['manifest']['dataset_version']!=artifact['dataset_version']:
        raise ValueError('데이터셋 버전 불일치')
    fit_ids=set(artifact['split']['fit']['record_ids'])
    actual=[row for row in dataset['records'] if row['record_id'] in fit_ids]
    if actual != artifact['fit_records']:
        raise ValueError('보정 표본이 원본/분할과 일치하지 않습니다.')
    if not artifact['validation']['research_ready']:
        if not (test_only and artifact['source_status']=='MOCK_TEST_ONLY' and not artifact['validation']['eligibility_issues']):
            raise ValueError('연구 실행 보류: '+str(artifact['validation']['eligibility_issues'])+' / '+artifact['source_status'])
    return EmpiricalModel(artifact),dataset
