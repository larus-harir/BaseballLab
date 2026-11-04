"""Limited plate-appearance PoC. Reward is explicitly a surrogate, not game wins."""
from dataclasses import asdict, dataclass
from random import Random

from baseball_lab.core.contracts import Observation, RuleSet
from baseball_lab.core.engine import State, transition

OBSERVATION_SCHEMA='empirical-count-v1'
ACTION_SCHEMA='empirical-take-swing-pitchtype-v1'
BATS=('take','swing')


@dataclass
class Appearance:
    result: str
    reward: int
    events: list[dict]


class EmpiricalEnvironment:
    def __init__(self,model,run_id):
        self.model,self.run_id=model,run_id

    def play(self,batter,pitcher,seed,episode_id,*,record=False):
        streams={role:Random(f'empirical-pa-v1:{seed}:{role}') for role in ('batter','pitcher','outcome')}
        state=State();rows=[]
        for pitch_number in range(1,1001):
            observation=Observation(state.balls,state.strikes)
            bat_probs=batter.probabilities(observation)
            pitch_probs=pitcher.probabilities(observation)
            bat=batter.act(observation,BATS,streams['batter'])
            pitch=pitcher.act(observation,self.model.pitch_types,streams['pitcher'])
            if bat not in BATS or pitch not in self.model.pitch_types:
                raise ValueError('미지원 행동')
            sampled=self.model.sample(state.balls,state.strikes,pitch,bat,streams['outcome'])
            event=sampled['event']
            state=State(state.balls,state.strikes,'reached') if event=='reached' else transition(state,event,RuleSet())
            reward=0 if state.result is None else 1 if state.result in ('walk','single','double','triple','home_run','reached') else -1
            if record:
                donor=sampled['sampled_record']
                rows.append({'event_id':f'{episode_id}:{pitch_number}','run_id':self.run_id,'episode_id':episode_id,
                             'pitch_number':pitch_number,'observed_state_batter':asdict(observation),
                             'observed_state_pitcher':asdict(observation),'batter_action':bat,'pitcher_action':pitch,
                             'batter_probabilities':{a:float(p) for a,p in zip(BATS,bat_probs)},
                             'pitcher_probabilities':{a:float(p) for a,p in zip(self.model.pitch_types,pitch_probs)},
                             'sampled_result':event,'terminal_result':state.result,'reward':reward,
                             'reward_kind':'PA_REACH_BASE_SURROGATE_NOT_GAME_WIN',
                             'source_status':'MODEL_SIMULATED','model_id':self.model.artifact['model_id'],
                             'model_version':self.model.artifact['model_version'],'dataset_version':self.model.artifact['dataset_version'],
                             'reference_record_ids':sampled['reference_record_ids'],'probabilities_used':sampled['probabilities'],
                             'probability_status':'EMPIRICALLY_ESTIMATED','probability_ci95':sampled['probability_intervals'],'support_n':sampled['support_n'],'backoff_level':sampled['backoff_level'],
                             'sampled_location':{k:donor[k] for k in ('plate_x','plate_z','sz_top','sz_bot','release_speed','release_speed_kmh','release_spin_rate')},
                             'location_status':'MODEL_SIMULATED','intended_location':None,
                             'arrival_support_n':sampled['arrival_support_n'],'arrival_backoff_level':sampled['arrival_backoff_level'],
                             'assumption_status':'UNVERIFIED_ASSUMPTION'})
            if state.result is not None:
                return Appearance(state.result,reward,rows)
        raise RuntimeError('안전 한계 초과. 임의 종료 결과나 보상을 만들지 않습니다.')
