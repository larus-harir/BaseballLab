"""Evidence-gated zero-sum PA learning with an explicitly limited surrogate reward."""
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from random import Random
import json
import platform
import numpy as np

from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.core.contracts import Observation, positive_integer
from baseball_lab.data.lineage import content_hash, utc_now, write_json
from baseball_lab.evaluation.metrics import wilson_interval
from baseball_lab.outcome.empirical import load_model
from baseball_lab.tracking.results import code_identity
from .environment import EmpiricalEnvironment, BATS, OBSERVATION_SCHEMA, ACTION_SCHEMA

FEATURE_NAMES=('bias','balls','strikes','two_strikes','three_balls')


def count_features(obs, role):
    return np.array([1.,obs.balls/3,obs.strikes/2,float(obs.strikes==2),float(obs.balls==3)],dtype=np.float64)


def neural(role, types, seed, hidden=24):
    return NeuralPolicy(role,seed,hidden,actions=BATS if role=='batter' else types,
                        feature_encoder=count_features,feature_names=FEATURE_NAMES,
                        observation_schema=OBSERVATION_SCHEMA,action_schema=ACTION_SCHEMA)


def restore(data, types):
    return NeuralPolicy.from_state_dict(data,actions=BATS if data['role']=='batter' else types,
            feature_encoder=count_features,feature_names=FEATURE_NAMES,observation_schema=OBSERVATION_SCHEMA,action_schema=ACTION_SCHEMA)


class FixedPolicy:
    def __init__(self,actions,style='random'):
        self.actions=tuple(actions);self.style=style
    def probabilities(self,obs):
        p=np.full(len(self.actions),1/len(self.actions))
        if self.style in ('take','swing'):
            p[:]=0;p[self.actions.index(self.style)]=1
        return p
    def act(self,obs,legal,rng):
        if tuple(legal)!=self.actions: raise ValueError('정책 행동 스키마 불일치')
        return rng.choices(self.actions,weights=self.probabilities(obs),k=1)[0]


@dataclass(frozen=True)
class ResearchConfig:
    episodes: int = 600
    seed: int = 20261104
    evaluate_every: int = 200
    evaluation_n: int = 100
    batch_size: int = 8
    learning_rate: float = .001

    def __post_init__(self):
        for key in ('episodes','evaluate_every','evaluation_n','batch_size'):
            positive_integer(getattr(self,key),key)
        if type(self.seed) is not int or not 0<self.learning_rate<=.1:
            raise ValueError('Invalid learning settings')


def policy_id(run_id,role,step):
    return f'{run_id}:{role}:{step}'


def evaluate(env,batter,pitcher,initial_bat,initial_pitch,n,seed,past=None):
    opponents=[('batter','무작위 구종',batter,FixedPolicy(env.model.pitch_types)),
               ('batter','학습 전 투수',batter,initial_pitch),
               ('pitcher','무작위 타자',FixedPolicy(BATS),pitcher),
               ('pitcher','항상 스윙 기준선',FixedPolicy(BATS,'swing'),pitcher),
               ('pitcher','학습 전 타자',initial_bat,pitcher)]
    if past:
        opponents.extend([('batter','과거 투수 '+past['pitcher'][0].rsplit(':',1)[-1]+'타석',batter,past['pitcher'][1]),
                          ('pitcher','과거 타자 '+past['batter'][0].rsplit(':',1)[-1]+'타석',past['batter'][1],pitcher)])
    results=[]
    for role,label,bat,pitch in opponents:
        successes=0
        for i in range(n):
            result=env.play(bat,pitch,seed+i,f'eval:{role}:{label}:{i}')
            successes += result.reward==(1 if role=='batter' else -1)
        results.append({'role':role,'opponent':label,'n':n,'successes':successes,'success_rate':successes/n,
                        'ci95':wilson_interval(successes,n),'source_status':'MODEL_SIMULATED',
                        'definition':'PA reaches base' if role=='batter' else 'PA prevents reaching base',
                        'seed_start':seed,'reward_kind':'PA_SURROGATE_NOT_GAME_WIN'})
    return results


def probes(batter,pitcher):
    result=[]
    for b in range(4):
        for s in range(3):
            obs=Observation(b,s)
            result.append({'balls':b,'strikes':s,'observed_state':asdict(obs),
                           'batter':{a:float(p) for a,p in zip(batter.actions,batter.probabilities(obs))},
                           'pitcher':{a:float(p) for a,p in zip(pitcher.actions,pitcher.probabilities(obs))},
                           'source_status':'MODEL_SIMULATED','probe_kind':'rule-valid fixed public state, not a historical play'})
    return result


def decision_summary(events):
    bat=Counter();pitch=Counter();first=Counter();by_count={}
    for e in events:
        role=e['train_role'];obs=e['observed_state_batter'];key=f"{obs['balls']}-{obs['strikes']}"
        group=by_count.setdefault(key,{'batter':Counter(),'pitcher':Counter()})
        if role=='batter':
            bat[e['batter_action']]+=1;group['batter'][e['batter_action']]+=1
            if e['pitch_number']==1:first[e['batter_action']]+=1
        else:
            pitch[e['pitcher_action']]+=1;group['pitcher'][e['pitcher_action']]+=1
    return {'learner_batter_decisions':dict(bat),'learner_pitcher_decisions':dict(pitch),
            'first_pitch_batter':dict(first),'by_count':{k:{r:dict(v) for r,v in g.items()} for k,g in by_count.items()},
            'source_status':'MODEL_SIMULATED','note':'Only the updated role is included for each training episode'}


def train(config,model_path,output,*,experiment_id='E01',progress=print,test_only=False):
    model,dataset=load_model(model_path,test_only=test_only)
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('결과 덮어쓰기 방지: 새 --output 폴더를 지정하세요.')
    output.mkdir(parents=True,exist_ok=True)
    run_id=content_hash({'config':asdict(config),'model_id':model.artifact['model_id'],'started_at':utc_now()})[:20]
    env=EmpiricalEnvironment(model,run_id)
    batter,pitcher=neural('batter',model.pitch_types,config.seed),neural('pitcher',model.pitch_types,config.seed+1)
    initial_bat,initial_pitch=batter.frozen(),pitcher.frozen()
    pools={'batter':[(policy_id(run_id,'batter',0),initial_bat)],'pitcher':[(policy_id(run_id,'pitcher',0),initial_pitch)]}
    rng=Random(config.seed)
    buffers={'batter':[],'pitcher':[]};baseline={'batter':0.,'pitcher':0.}
    history=[];window=[];global_steps={'batter':0,'pitcher':0};replay_sets=[]
    metadata={**code_identity(),'runtime':{'python':platform.python_version(),'numpy':np.__version__}}
    statuses={'source':'REAL_OBSERVED','model':'EMPIRICALLY_ESTIMATED','events':'MODEL_SIMULATED','causal_effect':'UNVERIFIED_ASSUMPTION'}
    if test_only: statuses={key:'MOCK_TEST_ONLY' for key in statuses}
    payload={'run_id':run_id,'child_experiment_id':experiment_id,'source_statuses':statuses,'run_status':'running',
             'research_executed':not test_only,'training_executed':False,'config':asdict(config),
             'started_at':utc_now(),'dataset_version':model.artifact['dataset_version'],'model_id':model.artifact['model_id'],
             'environment_version':{'model':model.artifact['model_version'],'observation':OBSERVATION_SCHEMA,'action':ACTION_SCHEMA,
                                    'ruleset':'basic-pa-v1','reward':'PA_REACH_BASE_SURROGATE_NOT_GAME_WIN',
                                    'unsupported_features':dataset['manifest']['unsupported_features'],'assumptions':model.artifact['assumptions']},
             'history':history,'lineage':dataset['manifest'],'validation':model.artifact['validation'],**metadata}

    def save_decision_version(role,policy):
        version=f'{run_id}:{role}:optimizer:{global_steps[role]}'
        write_json(output/'policy_versions'/f'{role}_{global_steps[role]:06d}.json',
                   {'policy_version_id':version,'model_id':model.artifact['model_id'],
                    'dataset_version':model.artifact['dataset_version'],'source_status':statuses['events'],
                    'policy':policy.state_dict()})
    save_decision_version('batter',batter);save_decision_version('pitcher',pitcher)

    def observe(step):
        batter.collect=pitcher.collect=False
        evaluation=evaluate(env,batter,pitcher,initial_bat,initial_pitch,config.evaluation_n,config.seed+1000000,past={r:pool[-1] for r,pool in pools.items()})
        event_rows=[]
        for i in range(8):
            result=env.play(batter,pitcher,config.seed+2000000+i,f'replay:{step}:{i}',record=True)
            for row in result.events:
                row.update({'checkpoint_step':step,'seed':config.seed+2000000+i,
                            'batter_policy_id':policy_id(run_id,'batter',step),'pitcher_policy_id':policy_id(run_id,'pitcher',step)})
                if test_only: row.update({'source_status':'MOCK_TEST_ONLY','probability_status':'MOCK_TEST_ONLY','location_status':'MOCK_TEST_ONLY'})
            event_rows.extend(result.events)
        replay_sets.append({'checkpoint_step':step,'seed_start':config.seed+2000000,'events':event_rows})
        entry={'checkpoint_step':step,'training_episodes':step,'optimizer_steps':dict(global_steps),
               'batter_policy_id':policy_id(run_id,'batter',step),'pitcher_policy_id':policy_id(run_id,'pitcher',step),
               'evaluation':evaluation,'probes':probes(batter,pitcher),'decisions':decision_summary(window),
               'opponent_pool':{role:[key for key,_ in pool] for role,pool in pools.items()},'source_status':statuses['events']}
        history.append(entry)
        snapshot={'checkpoint_version':'empirical-pa-policies-v1','run_id':run_id,'experiment_id':experiment_id,
                  'checkpoint_step':step,'source_status':statuses['events'],'dataset_version':model.artifact['dataset_version'],
                  'model_id':model.artifact['model_id'],'model_path':str(Path(model_path).resolve()),'config':asdict(config),
                  'observation_schema':OBSERVATION_SCHEMA,'action_schema':ACTION_SCHEMA,'pitch_types':list(model.pitch_types),
                  'opponent_pool':entry['opponent_pool'],'batter':batter.state_dict(),'pitcher':pitcher.state_dict(),**metadata}
        write_json(output/'checkpoints'/f'pa_{step:06d}.json',snapshot)
        payload['training_executed']=step>0
        write_json(output/'research.json',payload)
        write_json(output/'replays.json',replay_sets)
        from baseball_lab.tracking.evidence_report import write_report
        write_report(output,payload,dataset,model.artifact,replay_sets)
        progress(f"{'MOCK_TEST_ONLY · 테스트 전용' if test_only else '실제 기록 보정 모델'} · 출루 대리보상 학습 {step}/{config.episodes}타석 | "+' / '.join(f"{r['opponent']}({r['role']}): {r['success_rate']:.1%} N={r['n']}" for r in evaluation))

    observe(0)
    with (output/'events.jsonl').open('w',encoding='utf-8') as log:
        for step in range(1,config.episodes+1):
            role='batter' if step%2 else 'pitcher'
            other='pitcher' if role=='batter' else 'batter'
            learner=batter if role=='batter' else pitcher
            learner.decisions=[];learner.collect=True
            if rng.random()<.5:
                opponent_id,opponent=rng.choice(pools[other])
            else:
                opponent_id,opponent='fixed:uniform:'+other,FixedPolicy(model.pitch_types if other=='pitcher' else BATS)
            bat,pitch=(learner,opponent) if role=='batter' else (opponent,learner)
            result=env.play(bat,pitch,config.seed*100000+step,f'train:{step}',record=True)
            reward=result.reward if role=='batter' else -result.reward
            buffers[role].append((learner.decisions,reward-baseline[role]))
            baseline[role]=.95*baseline[role]+.05*reward
            learner.collect=False
            for event in result.events:
                event.update({'train_role':role,'training_episode':step,'seed':config.seed*100000+step,
                              'batter_policy_id':f'{run_id}:batter:optimizer:{global_steps[role]}' if role=='batter' else opponent_id,
                              'pitcher_policy_id':f'{run_id}:pitcher:optimizer:{global_steps[role]}' if role=='pitcher' else opponent_id,
                              'opponent_checkpoint_id':opponent_id,'learner_reward':reward if event['terminal_result'] else 0})
                if test_only: event.update({'source_status':'MOCK_TEST_ONLY','probability_status':'MOCK_TEST_ONLY','location_status':'MOCK_TEST_ONLY'})
                log.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n');window.append(event)
            checkpoint=step%config.evaluate_every==0 or step==config.episodes
            for target,policy in (('batter',batter),('pitcher',pitcher)):
                if len(buffers[target])>=config.batch_size or checkpoint:
                    if buffers[target]:
                        policy.update(buffers[target],config.learning_rate);global_steps[target]+=1;buffers[target].clear();save_decision_version(target,policy)
            if checkpoint:
                log.flush();observe(step);window.clear()
                for target,policy in (('batter',batter),('pitcher',pitcher)):
                    pools[target].append((policy_id(run_id,target,step),policy.frozen()))
                    if len(pools[target])>6:pools[target].pop(1)
    payload.update({'run_status':'completed','completed_at':utc_now()})
    write_json(output/'research.json',payload)
    from baseball_lab.tracking.evidence_report import write_report
    write_report(output,payload,dataset,model.artifact,replay_sets)
    progress(f'보고서: {(output/"report.html").resolve()}')
    return payload
