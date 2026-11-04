"""Two neural policies learn only terminal scoring/prevention reward."""
from dataclasses import asdict, dataclass
from random import Random
import math
import platform
import subprocess

import numpy as np
from baseball_lab.data.lineage import content_hash, write_json, utc_now
from .environment import (Observation, STATES, BAT_ACTIONS, PITCH_ACTIONS, key, policy, fit)


@dataclass(frozen=True)
class Config:
    episodes: int = 3000
    seeds: tuple = (41, 42, 43)
    evaluate_every: int = 1000
    evaluation_n: int = 500
    batch_size: int = 32

    def validate(self):
        if type(self.episodes) is not int or not 20 <= self.episodes <= 100000:
            raise ValueError('학습량: 20~100,000개의 상황 대결을 선택하세요.')
        if not self.seeds or len(set(self.seeds)) != len(self.seeds) or any(type(s) is not int or not 0 <= s <= 2**31-1 for s in self.seeds):
            raise ValueError('서로 다른 올바른 재현 번호가 필요합니다.')
        if self.evaluate_every < 1 or self.evaluation_n < 20 or self.batch_size < 1:
            raise ValueError('평가·업데이트 설정 범위를 확인하세요.')


class Fixed:
    def __init__(self, role, empirical=None):
        self.role, self.empirical = role, empirical

    def act(self, obs, legal, rng):
        if self.empirical is None:
            return legal[0]
        if self.role == 'pitcher':
            # Descriptive human IBB rate, not a target or a claim of human skill.
            rate = self.empirical.get(key(obs.outs, obs.bases, 'ibb'), 0.)
            return 'intentional_walk' if rng.random() < rate else 'challenge'
        rate = self.empirical.get(key(obs.outs, obs.bases, 'bunt'), 0.)
        return 'bunt_attempt' if 'bunt_attempt' in legal and rng.random() < rate else 'ordinary_turn'


def human_frequencies(dataset, boundary):
    from collections import Counter
    total = Counter(); bunts = Counter(); ibb = Counter()
    for r in dataset['records']:
        if boundary[0] <= r['date'] <= boundary[1]:
            state = (r['outs'], r['bases']); total[state] += 1
            bunts[state] += r['action'] == 'bunt_attempt'; ibb[state] += r['intentional_walk']
    return {key(o, b, a): counter[(o, b)]/total[(o, b)] if total[(o, b)] else 0.
            for o, b in STATES for a, counter in (('bunt', bunts), ('ibb', ibb))}


def interval(successes, n):
    p = successes/n; z = 1.959963984540054; d = 1+z*z/n
    mid = (p+z*z/(2*n))/d
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0., mid-radius), min(1., mid+radius)]


def evaluate(env, batter, pitcher, n, seed):
    wins = sum(env.play(batter, pitcher, seed+i*7919)[0] == 1 for i in range(n))
    return {'n': n, 'scored': wins, 'scoring_rate': wins/n, 'wilson_95': interval(wins, n),
            'environment_id': env.model_id,
            'uncertainty_scope': 'Monte Carlo only; excludes data/model/selection uncertainty.'}


def probes(env, batter, pitcher):
    return [{'outs': o, 'bases': b, 'bunt_probability': float(batter.probabilities(Observation(o,b), env.batter_actions(Observation(o,b)))[1]),
             'intentional_walk_probability': float(pitcher.probabilities(Observation(o,b), PITCH_ACTIONS)[1]),
             'bunt_supported': 'bunt_attempt' in env.batter_actions(Observation(o,b))} for o, b in STATES]


def assessments(env, pair, initial, past, human, n, seed):
    opponents = {'fixed': (Fixed('batter'), Fixed('pitcher')), 'initial': initial,
                 'past': past, 'third_human_frequency': (Fixed('batter', human), Fixed('pitcher', human))}
    rows = []
    for label, opponent in opponents.items():
        for role in ('batter', 'pitcher'):
            row = evaluate(env, pair[0] if role == 'batter' else opponent[0],
                           pair[1] if role == 'pitcher' else opponent[1], n, seed)
            rows.append({'learner_role': role, 'opponent': label, **row})
    rows.append({'learner_role': 'both', 'opponent': 'self', **evaluate(env, *pair, n, seed)})
    return rows


def train(dataset, start, end, output, config=Config(), *, test_only=False):
    from pathlib import Path
    from .report import report
    config.validate(); output = Path(output)
    if dataset['manifest']['source_status']!='REAL_OBSERVED' and not test_only:
        raise ValueError('실제 원천 자료만 연구에 사용할 수 있습니다. 테스트 자료는 연구로 실행하지 않습니다.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('기존 결과가 있는 폴더를 덮어쓰지 않습니다.')
    envs, model = fit(dataset, start, end)
    output.mkdir(parents=True, exist_ok=True)
    human = human_frequencies(dataset, model['split']['fit']['dates'])
    try:
        code_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        code_commit, dirty = 'unknown', True
    source_root = Path(__file__).resolve().parents[1]
    source_hash = content_hash({str(p.relative_to(source_root)): p.read_text(encoding='utf-8') for p in sorted(source_root.rglob('*.py'))})
    result = {'schema': 'E01-R1-research-v1', 'status': 'RUNNING', 'created_at': utc_now(),
              'source_status': 'MOCK_TEST_ONLY' if test_only else 'MODEL_SIMULATED', 'dataset': dataset['manifest'], 'model': model,
              'config': asdict(config), 'code_commit': code_commit, 'code_dirty': dirty, 'source_hash': source_hash,
              'runtime': {'python': platform.python_version(), 'numpy': np.__version__},
              'reward': {'offense_scores_at_least_one_run': 1, 'three_outs_without_scoring': -1,
                         'pitcher': 'negative of offense', 'intermediate': 0},
              'start_distribution': 'uniform over all 24 outs/base states; designed scenario distribution, not real-game frequency',
              'scope': 'One-run half-inning situation, not full-game wins; team-side coarse choices, not pitch biomechanics.',
              'assumptions': [
                  'Observed bunt-containing turns are not randomized bunt commands; hitter/defense/intent selection remains confounded.',
                  'State aggregates players, parks, count and score; observed transition transport to new policies is unverified.',
                  'Normal turns include automatic observed runner/fielding events; these are not learned actions.',
                  'Instant intentional walk suppresses pre-walk steals/wild pitches; a rule abstraction verified on isolated observed IBB events.',
                  'No pitch type/location/velocity/swing intention inferred. No pitch-by-pitch or full-game strategy claim.',
                  'Human-frequency opponent uses only fit-period descriptive rates and is not an independent real human team.',
                  'Checkpoint evaluation uses validation environment; final test environment is used only after learning, no model selection.',
                  'Monte Carlo intervals do not cover model misspecification, sampling error of donors or observational bias.'],
              'human_frequency_baseline': human, 'seeds': []}
    result['run_id'] = content_hash({'dataset': model['dataset_id'], 'models': [e.model_id for e in envs.values()],
                                     'config': asdict(config), 'source_hash': source_hash})
    write_json(output/'models.json', {name: env.serialize() for name, env in envs.items()})
    for seed in config.seeds:
        from collections import Counter
        rng = Random(seed); b, p = policy('batter', seed), policy('pitcher', seed+1)
        initial = (b.frozen(), p.frozen()); archived = [initial]; histories = []; batches = [[], []]; baselines = [0., 0.]
        observed = [Counter(), Counter()]; modes = Counter()
        changed = [list(v.copy() for v in agent.params) for agent in (b, p)]
        run = {'seed': seed, 'history': histories, 'checkpoints': [], 'replays': []}
        result['seeds'].append(run)

        def checkpoint(done):
            pair = (b.frozen(), p.frozen()); past = archived[-1]
            history = {'episodes': done, 'policy_probes': probes(envs['fit'], *pair),
                       'validation_evaluation': assessments(envs['validation'], pair, initial, past, human, config.evaluation_n, seed+100000),
                       'observed_learner_choices': {'batter': dict(observed[0]), 'pitcher': dict(observed[1])},
                       'training_opponents': dict(modes),
                       'optimizer_steps': {'batter': b.steps, 'pitcher': p.steps}}
            histories.append(history)
            path = output/'checkpoints'/f'seed_{seed}_episode_{done:06}.json'
            write_json(path, {'run_id': result['run_id'], 'dataset_id': model['dataset_id'],
                             'environment_id': envs['fit'].model_id, 'episodes': done,
                             'batter': b.state_dict(), 'pitcher': p.state_dict()})
            run['checkpoints'].append(str(path.relative_to(output)))
            # Same predefined states/seeds at each checkpoint allow observed before/after replay.
            run['replays'].append({'episodes': done, 'scenes': [
                {'start': list(state), 'reward': (game := envs['validation'].play(*pair, seed+700000+i, start=state, record=True))[0],
                 'events': game[1]} for i, state in enumerate(((0,0), (0,1), (1,4), (2,3)))]})
            archived.append(pair)
            write_json(output/'research.json', result); report(output, result)

        checkpoint(0)
        for episode in range(1, config.episodes+1):
            mode = rng.choices(('self', 'past_b', 'past_p', 'fixed_b', 'fixed_p'), weights=(4,1,1,1,1))[0]
            modes[mode] += 1
            pair = [b, p]; learning = [True, True]
            if mode != 'self':
                index = 0 if mode.endswith('_b') else 1
                pair[index] = rng.choice(archived)[index] if mode.startswith('past') else Fixed('batter' if index == 0 else 'pitcher')
                learning[index] = False
            for i, agent in enumerate((b, p)):
                agent.collect = learning[i]; agent.decisions = []
            reward, _ = envs['fit'].play(*pair, rng.randrange(2**31))
            for i, agent in enumerate((b, p)):
                if learning[i]:
                    value = reward if i == 0 else -reward
                    batches[i].append((list(agent.decisions), value-baselines[i]))
                    observed[i].update(agent.actions[d[1]] for d in agent.decisions)
            if episode % config.batch_size == 0 or episode == config.episodes or episode % config.evaluate_every == 0:
                for i, agent in enumerate((b, p)):
                    agent.update(batches[i])
                    if batches[i]:baselines[i] += .1*sum(adv for _, adv in batches[i])/len(batches[i])
                    batches[i] = []
            if episode % config.evaluate_every == 0 or episode == config.episodes:
                for agent in (b,p):agent.collect = False; agent.decisions = []
                print(f'학습 {episode}/{config.episodes}상황 · 재현 번호 {seed}', flush=True)
                checkpoint(episode)
        run['both_parameters_changed'] = all(any(not np.array_equal(old,new) for old,new in zip(before, agent.params)) for before,agent in zip(changed,(b,p)))
        if not run['both_parameters_changed']:
            raise RuntimeError('두 정책 모두의 실제 가중치 갱신을 확인하지 못했습니다.')
        final = (b.frozen(), p.frozen()); past = archived[max(1,len(archived)//2)]
        run['test_evaluation'] = assessments(envs['test'], final, initial, past, human, config.evaluation_n, seed+900000)
        run['initial_test_evaluation'] = assessments(envs['test'], initial, initial, initial, human, config.evaluation_n, seed+900000)
        control = envs['test'].bunt_effect_ablation()
        run['bunt_effect_ablation'] = {
            'source_status': 'UNVERIFIED_ASSUMPTION',
            'description': 'No retraining. Bunt donor transitions replaced by ordinary donors in the same state. Measures dependence on the observed action partition, not causal robustness.',
            'initial': evaluate(control, initial[0], Fixed('pitcher'), config.evaluation_n, seed+900000),
            'learned': evaluate(control, final[0], Fixed('pitcher'), config.evaluation_n, seed+900000)}
        run['cross_play'] = [{'batter_episode': histories[i]['episodes'], 'pitcher_episode': histories[j]['episodes'],
                              **evaluate(envs['test'], archived[i+1][0], archived[j+1][1], config.evaluation_n, seed+900000)}
                             for i in range(len(histories)) for j in range(len(histories))]
    result.update(status='COMPLETED', completed_at=utc_now())
    write_json(output/'research.json', result); report(output, result)
    return result
