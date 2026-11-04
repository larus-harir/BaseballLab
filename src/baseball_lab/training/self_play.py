"""Terminal-game REINFORCE against baselines and a historical snapshot pool."""
import json
import platform
import numpy as np
from dataclasses import asdict, dataclass
from pathlib import Path
from random import Random

from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.core.contracts import positive_integer
from baseball_lab.core.game import GameEngine, GameRules, Team, GameObservation, GAME_ACTION_SCHEMA, GAME_OBSERVATION_SCHEMA
from baseball_lab.evaluation.games import baseline_teams, evaluate_team
from baseball_lab.labels import korean
from baseball_lab.outcome.game import GameOutcome
from baseball_lab.tracking.results import code_identity


@dataclass(frozen=True)
class TrainingConfig:
    games: int = 600
    innings: int = 3
    seed: int = 20261104
    evaluate_every: int = 200
    evaluation_pairs: int = 12
    batch_size: int = 8
    hidden: int = 24
    learning_rate: float = .001

    def __post_init__(self):
        for name in ('games', 'innings', 'evaluate_every', 'evaluation_pairs', 'batch_size', 'hidden'):
            positive_integer(getattr(self, name), name)
        if type(self.seed) is not int or not 0 < self.learning_rate <= .1:
            raise ValueError('Invalid seed or learning rate')


def probes(innings):
    return [
        ('초구·주자 없음', GameObservation(0, 0, 1, innings, 0, (False, False, False), 0, 0, False, 0)),
        ('무사 1루·동점', GameObservation(0, 0, 2, innings, 0, (True, False, False), 0, 0, False, 30)),
        ('2스트라이크·주자 없음', GameObservation(1, 2, 2, innings, 1, (False, False, False), 0, 0, False, 30)),
        ('마지막 이닝·2점 뒤짐', GameObservation(0, 0, innings, innings, 1, (True, True, False), 0, 2, True, 80)),
        ('마지막 이닝·1점 앞섬', GameObservation(2, 1, innings, innings, 2, (False, True, False), 2, 1, False, 80)),
    ]


def probe_team(team, innings):
    result = []
    for label, observation in probes(innings):
        bat = team.batter.probabilities(observation)
        pitch = team.pitcher.probabilities(observation)
        kind = {key: 0. for key in ('fastball', 'breaking', 'changeup')}
        effort = {'절약 투구': 0., '보통 투구': 0., '전력 투구': 0.}
        zone = {'존 공략': 0., '유인구 목표': 0.}
        for action, probability in zip(team.pitcher.actions, pitch):
            kind[action.kind] += float(probability)
            effort[{-1: '절약 투구', 0: '보통 투구', 1: '전력 투구'}[action.effort]] += float(probability)
            zone['존 공략' if action.zone else '유인구 목표'] += float(probability)
        result.append({'situation': label, 'batter': {korean(action.value): float(p) for action, p in zip(team.batter.actions, bat)},
                       'pitch_type': {korean(k): v for k, v in kind.items()}, 'effort': effort, 'zone': zone})
    return result


def frozen(team, name):
    return Team(name, team.batter.frozen(), team.pitcher.frozen())


def checkpoint(team, config, games, metadata):
    return {'checkpoint_version': 'neural-team-v1', 'trained_games': games,
            'config': asdict(config), 'policy_version': f'game-{games}',
            'observation_schema': GAME_OBSERVATION_SCHEMA, 'action_schema': GAME_ACTION_SCHEMA,
            'training_league': 'synthetic_demo', 'ruleset': 'innings-v1',
            'calibration': 'synthetic-game-v1', 'source_data_version': 'synthetic-game-v1',
            'algorithm': 'two-hidden-layer-REINFORCE-terminal-win', 'seed': config.seed,
            **metadata, 'batter': team.batter.state_dict(), 'pitcher': team.pitcher.state_dict()}


def load_checkpoint(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if (data.get('checkpoint_version') != 'neural-team-v1' or data.get('observation_schema') != GAME_OBSERVATION_SCHEMA
            or data.get('action_schema') != GAME_ACTION_SCHEMA or data.get('calibration') != 'synthetic-game-v1'):
        raise ValueError('Incompatible team checkpoint')
    config = TrainingConfig(**data['config'])
    batter, pitcher = NeuralPolicy.from_state_dict(data['batter']), NeuralPolicy.from_state_dict(data['pitcher'])
    if batter.role != 'batter' or pitcher.role != 'pitcher':
        raise ValueError('Checkpoint policy role mismatch')
    return Team(f"학습 {data['trained_games']}경기", batter, pitcher), config, data


def train(config: TrainingConfig, output: Path, progress=print, *, experiment_id: str):
    if not experiment_id:
        raise ValueError("experiment_id is required")
    output = Path(output)
    if (output/'training.json').exists() or (output/'checkpoints').exists():
        raise ValueError('기존 학습 결과가 있습니다. --output으로 새 폴더를 지정하세요.')
    output.mkdir(parents=True, exist_ok=True)
    (output/'checkpoints').mkdir()
    metadata = {**code_identity(), "experiment_id": experiment_id, "runtime": {"python": platform.python_version(), "numpy": np.__version__}}
    engine = GameEngine(GameOutcome(), GameRules(config.innings))
    learner = Team('학습 팀', NeuralPolicy('batter', config.seed, config.hidden), NeuralPolicy('pitcher', config.seed+1, config.hidden))
    initial = frozen(learner, 'initial')
    pool = [initial]
    fixed = baseline_teams()
    rng = Random(config.seed)
    history, pending_bat, pending_pitch = [], [], []
    baseline = 0.
    rewards, opponents_seen = [], {}

    def observe(games, losses=None):
        learner.batter.collect = learner.pitcher.collect = False
        evaluations = evaluate_team(engine, learner, [*fixed, initial], seed=config.seed+1000000, pairs=config.evaluation_pairs)
        historical = evaluate_team(engine, learner, pool[-2:], seed=config.seed+2000000, pairs=config.evaluation_pairs)
        entry = {'games': games, 'evaluation': evaluations, 'historical_evaluation': historical,
                 'probes': probe_team(learner, config.innings), 'losses': losses,
                 'training_window': {'games': len(rewards), 'wins': rewards.count(1), 'losses': rewards.count(-1), 'draws': rewards.count(0)},
                 'opponents_seen': dict(opponents_seen), 'reward_baseline': baseline}
        history.append(entry)
        (output/'checkpoints'/f'game_{games:06d}.json').write_text(
            json.dumps(checkpoint(learner, config, games, metadata), ensure_ascii=False), encoding='utf-8')
        payload = {'experiment_id': experiment_id, 'training_executed': games > 0, 'algorithm': 'REINFORCE',
                   'config': asdict(config), 'reward': {'win': 1, 'loss': -1, 'draw': 0, 'intermediate': 0},
                   'profile': 'synthetic_demo', 'calibration': 'synthetic-game-v1',
                   'game_rules': asdict(engine.rules), 'league_profile': asdict(engine.profile), 'status': 'completed' if games == config.games else 'running', 'attributes': asdict(engine.outcome.attributes),
                   'evaluation_seed_start': config.seed+1000000, 'history': history, **metadata}
        (output/'training.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        from baseball_lab.tracking.learning_report import write_report
        write_report(output, payload, {'events': []})
        comparison = ' / '.join(f"{korean(e['opponent'])}: {e['wins']}승 {e['losses']}패 {e['draws']}무" for e in evaluations)
        progress(f'학습 {games:,}/{config.games:,}경기 | 고정 조건 평가 | {comparison}')
        return payload

    progress(f'{korean(experiment_id)} | {config.innings}이닝 경기 | 보상: 승리 +1 / 패배 -1 / 무승부 0')
    payload = observe(0)
    latest_losses = None
    for game_number in range(1, config.games+1):
        opponent = rng.choice(fixed) if rng.random() < .5 else rng.choice(pool)
        opponents_seen[opponent.name] = opponents_seen.get(opponent.name, 0)+1
        learner.batter.decisions = []; learner.pitcher.decisions = []
        learner.batter.collect = learner.pitcher.collect = True
        side = game_number % 2
        seed = config.seed*100000 + game_number
        result = engine.play(learner, opponent, seed) if side == 0 else engine.play(opponent, learner, seed)
        reward = result.reward(side)
        advantage = reward-baseline
        pending_bat.append((learner.batter.decisions, advantage))
        pending_pitch.append((learner.pitcher.decisions, advantage))
        baseline = .95*baseline+.05*reward
        rewards.append(reward)
        if len(pending_bat) >= config.batch_size or game_number % config.evaluate_every == 0 or game_number == config.games:
            latest_losses = {'batter': learner.batter.update(pending_bat, config.learning_rate),
                             'pitcher': learner.pitcher.update(pending_pitch, config.learning_rate)}
            pending_bat.clear(); pending_pitch.clear()
        if game_number % config.evaluate_every == 0 or game_number == config.games:
            payload = observe(game_number, latest_losses)
            pool.append(frozen(learner, f'과거 {game_number}경기 모델'))
            if len(pool) > 6:
                pool.pop(1)  # Always retain the original untrained opponent.
            rewards.clear()
    learner.batter.collect = learner.pitcher.collect = False
    replay = engine.play(learner, fixed[1], config.seed+3000000, record=True)
    (output/'replay.json').write_text(json.dumps(asdict(replay), ensure_ascii=False, indent=2), encoding='utf-8')
    from baseball_lab.tracking.learning_report import write_report
    write_report(output, payload, asdict(replay))
    progress(f'학습 완료. 전략 변화 보고서: {(output/"report.html").resolve()}')
    progress(f'학습된 정책: {(output/"checkpoints"/f"game_{config.games:06d}.json").resolve()}')
    return payload
