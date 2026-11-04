"""Evaluate and replay a saved policy, without any optimization or weight changes."""
import json
from dataclasses import asdict
from pathlib import Path

from baseball_lab.core.game import GameEngine, GameRules
from baseball_lab.evaluation.games import baseline_teams, evaluate_team
from baseball_lab.outcome.game import GameOutcome
from baseball_lab.tracking.learning_report import write_report
from baseball_lab.labels import korean
from .self_play import load_checkpoint, probe_team


def replay_checkpoint(checkpoint, output: Path, pairs=12):
    team, config, data = load_checkpoint(checkpoint)
    output.mkdir(parents=True, exist_ok=True)
    engine = GameEngine(GameOutcome(), GameRules(config.innings))
    opponents = baseline_teams()
    evaluations = evaluate_team(engine, team, opponents, seed=config.seed+1000000, pairs=pairs)
    replay = asdict(engine.play(team, opponents[1], config.seed+3000000, record=True))
    entry = {'games': data['trained_games'], 'evaluation': evaluations, 'probes': probe_team(team, config.innings)}
    report_config = asdict(config)
    report_config['games'] = data['trained_games']
    payload = {'experiment_id': data['experiment_id'], 'evaluation_only': True, 'config': report_config, 'game_rules': asdict(engine.rules),
               'history': [entry], 'checkpoint': str(checkpoint), 'training_executed': False}
    (output/'evaluation.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'replay.json').write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding='utf-8')
    write_report(output, payload, replay)
    for item in evaluations:
        print(f"{korean(item['opponent'])}: {item['wins']}승 {item['losses']}패 {item['draws']}무")
    print(f'저장 정책 재평가 완료: {(output/"report.html").resolve()}')
    return payload
