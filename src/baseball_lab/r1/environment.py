"""Empirical turn transitions and a bounded one-run scoring contest.

This is an observational, aggregated Markov model, not an identified causal
model of commanding a bunt. No pitch parameters or player ratings are invented.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from random import Random

import numpy as np
from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.data.lineage import content_hash
from .data import walk

BAT_ACTIONS = ('ordinary_turn', 'bunt_attempt')
PITCH_ACTIONS = ('challenge', 'intentional_walk')
FEATURES = ('bias', 'outs', 'first', 'second', 'third')
OBS_SCHEMA = 'r1-outs-bases-public-v1'
ACTION_SCHEMA = 'r1-observed-turn-versus-intentional-walk-v1'
STATES = tuple((o, b) for o in range(3) for b in range(8))


@dataclass(frozen=True)
class Observation:
    outs: int
    bases: int


def features(obs, role):
    return np.array([1., obs.outs/2, *(float(bool(obs.bases & (1 << i))) for i in range(3))])


def policy(role, seed):
    return NeuralPolicy(role, seed, actions=BAT_ACTIONS if role == 'batter' else PITCH_ACTIONS,
                        feature_encoder=features, feature_names=FEATURES,
                        observation_schema=OBS_SCHEMA, action_schema=ACTION_SCHEMA)


def restore(data):
    return NeuralPolicy.from_state_dict(data, actions=BAT_ACTIONS if data['role'] == 'batter' else PITCH_ACTIONS,
                                        feature_encoder=features, feature_names=FEATURES,
                                        observation_schema=OBS_SCHEMA, action_schema=ACTION_SCHEMA)


def key(outs, bases, action):
    return f'{outs}:{bases}:{action}'


def outcome(row):
    return (row['outs_added'], row['end_bases'], row['runs'])


class Environment:
    def __init__(self, rows, legal, name):
        self.name = name
        self.legal = legal
        self.cells = defaultdict(list)
        for row in rows:
            if not row['intentional_walk']:
                self.cells[key(row['outs'], row['bases'], row['action'])].append(row)
        for outs, bases in STATES:
            for action in self.legal[key(outs, bases, 'legal')]:
                if not self.cells[key(outs, bases, action)]:
                    raise ValueError(f'{name}: {outs}아웃/주자코드 {bases}/{action} 실제 표본이 없습니다.')
        self.model_id = content_hash({'name': name, 'legal': legal,
                                      'records': [r['record_id'] for r in rows]})

    def batter_actions(self, obs):
        return tuple(self.legal[key(obs.outs, obs.bases, 'legal')])

    def step(self, obs, batter_action, pitcher_action, rng):
        if batter_action not in self.batter_actions(obs) or pitcher_action not in PITCH_ACTIONS:
            raise ValueError('Unsupported action')
        if pitcher_action == 'intentional_walk':
            bases, runs = walk(obs.bases)
            return Observation(obs.outs, bases), runs, {'source_status': 'RULE_DERIVED', 'rule': 'forced advance on intentional walk'}
        row = rng.choice(self.cells[key(obs.outs, obs.bases, batter_action)])
        return Observation(obs.outs+row['outs_added'], row['end_bases']), row['runs'], {
            'source_status': 'EMPIRICALLY_ESTIMATED', 'donor_record_id': row['record_id'],
            'donor_game_id': row['game_id'], 'donor_event_codes': row['event_codes'],
            'note': 'Observed transition resampled in a new simulated context; not the original game.'}

    def play(self, batter, pitcher, seed, *, start=None, record=False):
        rng = Random(seed)
        obs = Observation(*(start if start is not None else rng.choice(STATES)))
        events = []
        for turn in range(128):
            ba = self.batter_actions(obs)
            # Both choose from the same pre-turn public state; neither sees the other's choice.
            b = batter.act(obs, ba, rng); p = pitcher.act(obs, PITCH_ACTIONS, rng)
            if b not in ba or p not in PITCH_ACTIONS:
                raise ValueError('Illegal policy action')
            nxt, runs, evidence = self.step(obs, b, p, rng)
            if record:
                events.append({'turn': turn+1, 'before': vars(obs), 'after': vars(nxt),
                               'batter_action': b, 'pitcher_action': p, 'runs': runs,
                               'batter_probabilities': dict(zip(BAT_ACTIONS, batter.probabilities(obs, ba))) if hasattr(batter, 'probabilities') else None,
                               'pitcher_probabilities': dict(zip(PITCH_ACTIONS, pitcher.probabilities(obs, PITCH_ACTIONS))) if hasattr(pitcher, 'probabilities') else None,
                               'source_status': 'MODEL_SIMULATED', 'transition': evidence})
            if runs > 0 or nxt.outs == 3:
                return (1 if runs > 0 else -1), events
            obs = nxt
        raise RuntimeError('128턴 안전 한도: 결과를 승패로 만들지 않고 실행을 중단합니다.')

    def serialize(self):
        return {'model_id': self.model_id, 'name': self.name,
                'cells': {k: {'n': len(rows), 'transitions': [dict(outs_added=t[0], end_bases=t[1], runs=t[2], n=n)
                          for t, n in sorted(Counter(map(outcome, rows)).items())]} for k, rows in sorted(self.cells.items())}}

    def bunt_effect_ablation(self):
        """Control: replace bunt donors with normal-turn donors, without retraining.

        This tests dependence on the observational action split. It is not an
        alternative empirical claim about real bunts or a causal correction.
        """
        import copy
        control = copy.copy(self)
        control.cells = dict(self.cells)
        for outs, bases in STATES:
            control.cells[key(outs, bases, 'bunt_attempt')] = self.cells[key(outs, bases, 'ordinary_turn')]
        control.name = 'UNVERIFIED_ASSUMPTION_no_bunt_effect_control'
        control.model_id = content_hash({'base': self.model_id, 'control': control.name})
        return control


def diagnostic(train, rows):
    groups = defaultdict(list)
    for r in rows:
        if not r['intentional_walk']:
            groups[key(r['outs'], r['bases'], r['action'])].append(r)
    result = []; supported = 0; weighted_tv = 0; unseen = 0
    for k, target in sorted(groups.items()):
        outs, bases, action = k.split(':')
        if action not in train.legal[key(int(outs), int(bases), 'legal')]:
            continue
        fit = train.cells[k]; a = Counter(map(outcome, fit)); b = Counter(map(outcome, target))
        tv = sum(abs(a[t]/len(fit)-b[t]/len(target)) for t in a.keys() | b.keys())/2
        missing = sum(n for t, n in b.items() if not a[t])
        run_error = sum(t[2]*n for t, n in a.items())/len(fit)-sum(t[2]*n for t, n in b.items())/len(target)
        result.append({'cell': k, 'fit_n': len(fit), 'evaluation_n': len(target), 'total_variation': tv,
                       'mean_runs_error': run_error, 'unseen_outcomes': missing})
        supported += len(target); weighted_tv += tv*len(target); unseen += missing
    return {'supported_n': supported, 'all_n': len(rows), 'weighted_total_variation': weighted_tv/supported if supported else None,
            'unseen_outcomes': unseen, 'cells': result,
            'interpretation': 'Descriptive predictive check, not proof of causal transport or real-game validity.'}


def fit(dataset, start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first.year != 2024 or last.year != 2024 or first > last:
        raise ValueError('현재 실제 연결은 2024년 정규시즌입니다. 시작·종료 날짜를 확인하세요.')
    rows = [r for r in dataset['records'] if start <= r['date'] <= end]
    dates = sorted({r['date'] for r in rows})
    if len(dates) < 3:
        raise ValueError('모델 만들기·검사·독립 확인에 사용할 실제 경기 날짜가 부족합니다. 기간을 넓혀 주세요.')
    before, test_from = dates[max(1, int(len(dates)*.6))], dates[min(len(dates)-1, max(2, int(len(dates)*.8)))]
    parts = {'fit': [r for r in rows if r['date'] < before],
             'validation': [r for r in rows if before <= r['date'] < test_from],
             'test': [r for r in rows if test_from <= r['date']]}
    legal = {}; support = []
    for outs, bases in STATES:
        counts = {part: Counter(r['action'] for r in records if r['outs'] == outs and r['bases'] == bases and not r['intentional_walk'])
                  for part, records in parts.items() if part != 'test'}
        if counts['fit']['ordinary_turn'] < 30 or counts['validation']['ordinary_turn'] < 10:
            raise ValueError(f'{outs}아웃/주자코드 {bases}의 일반 타석 표본이 부족합니다. 선택 기간을 넓혀 주세요.')
        allowed = ['ordinary_turn']
        if counts['fit']['bunt_attempt'] >= 30 and counts['validation']['bunt_attempt'] >= 5:
            allowed.append('bunt_attempt')
        legal[key(outs, bases, 'legal')] = allowed
        support.append({'outs': outs, 'bases': bases, 'fit': dict(counts['fit']), 'validation': dict(counts['validation']), 'legal': allowed})
    envs = {name: Environment(records, legal, name) for name, records in parts.items()}
    game_sets = [{r['game_id'] for r in records} for records in parts.values()]
    if any(game_sets[i] & game_sets[j] for i in range(3) for j in range(i+1, 3)):
        raise ValueError('Game leakage between partitions')
    return envs, {'dataset_id': dataset['manifest']['dataset_id'], 'selected_dates': [start, end],
                  'date_semantics': 'Retrosheet game ID scheduled date; resumed games remain grouped with original game.',
                  'split': {name: {'dates': [min(r['date'] for r in records), max(r['date'] for r in records)],
                                   'n': len(records), 'games': len({r['game_id'] for r in records}),
                                   'record_ids_hash': content_hash([r['record_id'] for r in records])} for name, records in parts.items()},
                  'support': support, 'legal_actions_selected_without_test': True,
                  'validation': diagnostic(envs['fit'], parts['validation']), 'test': diagnostic(envs['fit'], parts['test'])}
