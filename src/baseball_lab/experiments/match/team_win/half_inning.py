"""Three-out run maximization, using the existing observed-turn engine.

Unlike R1 this does not terminate at the first run. Neither reward shaping nor
invented pitch outcomes enter learning. Donor selection remains observational.
"""
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from random import Random
import math
import platform
import subprocess

import numpy as np
from baseball_lab.data.lineage import content_hash, utc_now, write_json
from baseball_lab.r1.environment import Observation, BAT_ACTIONS, PITCH_ACTIONS, fit, policy
from .training import Config, Fixed, human_frequencies, probes

SCHEMA = 'Match-half-inning-research-v1'


def completion_aligned(dataset, dates):
    """Whole games enter a partition only after their last actual play date.

    Return a new in-memory view. Native records/caches and legacy R1 semantics
    are untouched. An incomplete date map is an error, never a scheduled-date
    fallback for the new experiment.
    """
    # A walk-off can censor a multi-run hit or a turn before three outs. Late
    # innings also introduce automatic runners. Do not transplant these into an
    # always-completed, bases-empty regulation half inning. Keep the source
    # intact and explicitly version the stricter donor population.
    mock = dataset['manifest']['source_status']=='MOCK_TEST_ONLY'
    ends = {}
    for row in dataset['records']:
        inning = row.get('inning',1) if mock else row['inning']
        bottom = row.get('bottom',0) if mock else row['bottom']
        ends[(row['game_id'],inning,bottom)] = row['outs']+row['outs_added']
    records = []; exclusions = Counter()
    for row in dataset['records']:
        raw = dates.get(row['game_id'])
        if not raw or len(raw) != 8 or not raw.isdigit():
            raise ValueError('실제 경기 종료 날짜를 확인할 수 없습니다.')
        aligned = f'{raw[:4]}-{raw[4:6]}-{raw[6:]}'
        inning = row.get('inning',1) if mock else row['inning']
        bottom = row.get('bottom',0) if mock else row['bottom']
        if not 1<=inning<=8:
            exclusions['ninth_or_extra_inning']+=1;continue
        if ends[(row['game_id'],inning,bottom)]!=3:
            exclusions['unfinished_half_inning']+=1;continue
        records.append({**row, 'date': aligned})
    if not records:raise ValueError('세 아웃까지 확인된 정규 이닝 기록이 없습니다.')
    population={'version':'completed-regulation-innings-1-to-8-v1', 'used_segments':len(records),
                'excluded_segments':dict(exclusions),
                'reason':'Exclude ninth/extra innings and incomplete halves to avoid walk-off censoring and automatic-runner transport.'}
    manifest = {**dataset['manifest'], 'original_dataset_id': dataset['manifest']['dataset_id'],
                'source_records_checksum':dataset['manifest'].get('records_checksum'),
                'records_checksum':content_hash(records),'used_segments':len(records),
                'date_semantics': 'whole game aligned to last actual recorded play date',
                'donor_population':population,
                'dataset_id': content_hash({'source': dataset['manifest']['dataset_id'], 'completion_dates': dates,
                                           'population':population,'records':content_hash([r['record_id'] for r in records])})}
    return {**dataset, 'records': records, 'manifest': manifest}


def play(env, batter, pitcher, seed, *, record=False):
    rng = Random(seed); obs = Observation(0, 0); total = 0; events = []
    if hasattr(env,'begin'):env.begin(rng)
    for turn in range(128):
        legal = env.batter_actions(obs)
        b = batter.act(obs, legal, rng); p = pitcher.act(obs, PITCH_ACTIONS, rng)
        nxt, runs, evidence = env.step(obs, b, p, rng)
        total += runs
        if record:
            events.append({'turn': turn+1, 'before': vars(obs), 'after': vars(nxt),
                           'batter_action': b, 'pitcher_action': p, 'runs': runs, 'total_runs': total,
                           'batter_probabilities': dict(zip(BAT_ACTIONS, batter.probabilities(obs, legal))) if hasattr(batter, 'probabilities') else None,
                           'pitcher_probabilities': dict(zip(PITCH_ACTIONS, pitcher.probabilities(obs, PITCH_ACTIONS))) if hasattr(pitcher, 'probabilities') else None,
                           'source_status': 'MODEL_SIMULATED', 'transition': evidence})
        if nxt.outs >= 3:
            return total, events
        obs = nxt
    raise RuntimeError('128턴 안전 한도: 끝나지 않은 이닝을 점수·승패로 확정하지 않습니다.')


def evaluate(env, batter, pitcher, n, seed):
    values = [play(env, batter, pitcher, seed+i*7919)[0] for i in range(n)]
    avg = sum(values)/n
    se = math.sqrt(sum((v-avg)**2 for v in values)/(n-1)/n)
    return {'n': n, 'mean_runs': avg, 'total_runs': sum(values), 'runs_by_inning': values,
            'mean_95_mc': [max(0., avg-1.96*se), avg+1.96*se], 'environment_id': env.model_id,
            'uncertainty_scope': 'Approximate Monte Carlo interval only; not donor/model/causal uncertainty.'}


def assessments(env, pair, initial, past, human, n, seed):
    opponents = {'fixed': (Fixed('batter'), Fixed('pitcher')), 'initial': initial,
                 'past': past, 'third_human_frequency': (Fixed('batter', human), Fixed('pitcher', human))}
    rows = []
    for name, opponent in opponents.items():
        for role in ('batter', 'pitcher'):
            rows.append({'learner_role': role, 'opponent': name,
                         **evaluate(env, pair[0] if role == 'batter' else opponent[0],
                                    pair[1] if role == 'pitcher' else opponent[1], n, seed)})
    rows.append({'learner_role': 'both', 'opponent': 'self', **evaluate(env, *pair, n, seed)})
    return rows


def train(dataset, start, end, output, config=Config(), *, test_only=False, evidence=None,prepared=None):
    from ..reporting.inning import report
    config.validate(); output = Path(output)
    if dataset['manifest']['source_status'] != 'REAL_OBSERVED' and not test_only:
        raise ValueError('실제 원천 자료만 연구에 사용할 수 있습니다.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('기존 결과가 있는 폴더를 덮어쓰지 않습니다.')
    if not test_only and 'original_dataset_id' not in dataset['manifest']:
        raise ValueError('경기 종료일 정렬을 먼저 확인해야 합니다.')
    envs, model = prepared if prepared is not None else fit(dataset, start, end)
    model['date_semantics'] = dataset['manifest'].get('date_semantics', 'MOCK_TEST_ONLY')
    human = human_frequencies(dataset, model['split']['fit']['dates'])
    output.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[3]
    source_hash = content_hash({str(p.relative_to(source_root)): p.read_text(encoding='utf-8') for p in sorted(source_root.rglob('*.py'))})
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = 'unknown', True
    result = {'schema': SCHEMA, 'status': 'RUNNING', 'created_at': utc_now(),
              'source_status': 'MOCK_TEST_ONLY' if test_only else 'MODEL_SIMULATED',
              'dataset': dataset['manifest'], 'model': model, 'config': asdict(config),
              'code_commit': commit, 'code_dirty': dirty, 'source_hash': source_hash,
              'runtime': {'python': platform.python_version(), 'numpy': np.__version__},
              'reward': {'offense': 'total runs until three outs', 'defense': 'negative of total runs', 'intermediate_shaping': 0},
              'start_state': {'outs': 0, 'bases': 0}, 'human_frequency_baseline': human,
              'data_evidence': evidence or {}, 'seeds': [],
              'scope': 'Three-out offensive half inning, not a nine-inning game or pitch-level policy.',
              'assumptions': [
                  'Ordinary turns include observed batting, runner and fielding events; these are not separate learned actions.',
                  'Bunt donors are observational and confounded by player/situation selection, not randomized bunt commands.',
                  'Players, count, parks and score are aggregated. Transport to new policies is not causally established.',
                  'Donors use completed first-through-eighth regulation innings; late/incomplete halves are excluded to avoid censored walk-offs and extra-inning runner rules.',
                  'Intentional walk is forced advance by rule; it omits possible pre-walk events.',
                  'Human opponent uses only fit-period observed action frequencies, not independent human skill.',
                  'Validation checkpoints do not select models; final test is opened after training.',
                  'Intervals cover simulation draws only, not finite donors or model uncertainty.']}
    result['run_id'] = content_hash({'schema': SCHEMA, 'dataset': model['dataset_id'], 'config': asdict(config), 'source_hash': source_hash})
    write_json(output/'models.json', {k: e.serialize() for k,e in envs.items()})
    for seed in config.seeds:
        exposure_before=Counter(getattr(envs['fit'],'episode_counts',{}))
        rng = Random(seed); b,p = policy('batter',seed),policy('pitcher',seed+1)
        initial = (b.frozen(),p.frozen()); archived = [initial]; histories = []
        batches = [[],[]]; baselines = [0.,0.]; observed = [Counter(),Counter()]; modes = Counter()
        before = [[v.copy() for v in agent.params] for agent in (b,p)]
        run = {'seed':seed,'history':histories,'checkpoints':[],'replays':[]}; result['seeds'].append(run)

        def checkpoint(done):
            pair = (b.frozen(),p.frozen())
            histories.append({'episodes':done, 'policy_probes':probes(envs['fit'],*pair),
                'league_exposure':dict(Counter(getattr(envs['fit'],'episode_counts',{}))-exposure_before),
                'validation_evaluation':assessments(envs['validation'],pair,initial,archived[-1],human,config.evaluation_n,seed+100000),
                'observed_learner_choices':{'batter':dict(observed[0]),'pitcher':dict(observed[1])},
                'training_opponents':dict(modes),'optimizer_steps':{'batter':b.steps,'pitcher':p.steps}})
            path = output/'checkpoints'/f'seed_{seed}_episode_{done:06}.json'
            write_json(path,{'run_id':result['run_id'],'dataset_id':model['dataset_id'], 'reward_schema':SCHEMA,
                             'episodes':done,'batter':b.state_dict(),'pitcher':p.state_dict()})
            run['checkpoints'].append(str(path.relative_to(output)))
            runs,events = play(envs['validation'],*pair,seed+700000,record=True)
            run['replays'].append({'episodes':done,'runs':runs,'events':events})
            archived.append(pair)
            write_json(output/'research.json',result); report(output,result)

        checkpoint(0)
        for episode in range(1,config.episodes+1):
            mode = rng.choices(('self','past_b','past_p','fixed_b','fixed_p'),weights=(4,1,1,1,1))[0]
            modes[mode] += 1; pair = [b,p]; learning = [True,True]
            if mode != 'self':
                i = 0 if mode.endswith('_b') else 1
                pair[i] = rng.choice(archived)[i] if mode.startswith('past') else Fixed('batter' if i==0 else 'pitcher')
                learning[i] = False
            for i,agent in enumerate((b,p)):
                agent.collect = learning[i]; agent.decisions = []
            runs,_ = play(envs['fit'],*pair,rng.randrange(2**31))
            for i,agent in enumerate((b,p)):
                if learning[i]:
                    value = runs if i==0 else -runs
                    batches[i].append((list(agent.decisions),value-baselines[i]))
                    observed[i].update(agent.actions[d[1]] for d in agent.decisions)
            if episode % config.batch_size==0 or episode==config.episodes or episode % config.evaluate_every==0:
                for i,agent in enumerate((b,p)):
                    agent.update(batches[i])
                    if batches[i]: baselines[i] += .1*sum(v for _,v in batches[i])/len(batches[i])
                    batches[i] = []
            if episode % config.evaluate_every==0 or episode==config.episodes:
                for agent in (b,p): agent.collect=False; agent.decisions=[]
                print(f'학습 {episode}/{config.episodes}상황 · 재현 번호 {seed}',flush=True)
                checkpoint(episode)
        run['both_parameters_changed'] = all(any(not np.array_equal(x,y) for x,y in zip(old,agent.params)) for old,agent in zip(before,(b,p)))
        if not run['both_parameters_changed']: raise RuntimeError('두 정책의 가중치 갱신을 확인하지 못했습니다.')
        run['league_exposure']=dict(Counter(getattr(envs['fit'],'episode_counts',{}))-exposure_before)
        final = (b.frozen(),p.frozen()); past = archived[max(1,len(archived)//2)]
        run['test_evaluation'] = assessments(envs['test'],final,initial,past,human,config.evaluation_n,seed+900000)
        run['initial_test_evaluation'] = assessments(envs['test'],initial,initial,initial,human,config.evaluation_n,seed+900000)
        if hasattr(envs['test'],'for_league'):
            run['per_league_evaluation']=[]
            for league in envs['test'].mixture:
                domain=envs['test'].for_league(league)
                for role in ('batter','pitcher'):
                    before_pair=(initial[0],Fixed('pitcher')) if role=='batter' else (Fixed('batter'),initial[1])
                    after_pair=(final[0],Fixed('pitcher')) if role=='batter' else (Fixed('batter'),final[1])
                    run['per_league_evaluation'].append({'league':league,'role':role,
                        'initial':evaluate(domain,*before_pair,config.evaluation_n,seed+900000),
                        'learned':evaluate(domain,*after_pair,config.evaluation_n,seed+900000)})
        control = envs['test'].bunt_effect_ablation()
        run['bunt_effect_ablation'] = {'source_status':'UNVERIFIED_ASSUMPTION',
            'initial':evaluate(control,initial[0],Fixed('pitcher'),config.evaluation_n,seed+900000),
            'learned':evaluate(control,final[0],Fixed('pitcher'),config.evaluation_n,seed+900000)}
    result.update(status='COMPLETED',completed_at=utc_now())
    write_json(output/'research.json',result); report(output,result)
    return result
