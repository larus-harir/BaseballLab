"""End-to-end checks of reusable research paths, not just baseline class methods."""

import csv
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from random import Random
from unittest.mock import patch

import pytest

from baseball_lab.agents.baselines import Batter
from baseball_lab.agents.registry import PolicyEntry, baseline_registry
from baseball_lab.core.contracts import (
    ACTION_SCHEMA, OBSERVATION_SCHEMA, BatAction, LeagueProfile, Observation,
    OutcomeContext, PitchAction, PlayerAttributes, RuleSet,
)
from baseball_lab.core.engine import Engine, State, transition
from baseball_lab.evaluation.matches import MatchSpec, evaluate
from baseball_lab.experiments.config import ExperimentConfig
from baseball_lab.experiments.runner import run_experiment
from baseball_lab.outcome.synthetic import SyntheticOutcome
from baseball_lab.tracking.results import code_identity

ROOT = Path(__file__).resolve().parents[1]


def config(**overrides):
    raw = {"seed": 7, "plate_appearances": 20,
           "batters": ["random", "patient"], "pitchers": ["random"]}
    raw.update(overrides)
    return ExperimentConfig.from_dict(raw)


def engine():
    return Engine(RuleSet(), LeagueProfile(), SyntheticOutcome())


@pytest.mark.parametrize('raw', [
    {"plate_appearances": 0}, {"plate_appearances": 1.5}, {"plate_appearances": True},
    {"seeds": []}, {"seeds": [1, 1]}, {"seeds": [True]},
    {"batters": []}, {"batters": ["random", "random"]},
    {"pitchers": "random"}, {"typo": 1}, {"attributes": {"contact": float('nan')}},
])
def test_invalid_configuration(raw):
    with pytest.raises(ValueError):
        config(**raw)


def test_seed_formats_and_roundtrip():
    a = config()
    assert ExperimentConfig.from_dict(a.to_dict()) == a
    raw = a.to_dict()
    raw['seed'] = 1
    with pytest.raises(ValueError):
        ExperimentConfig.from_dict(raw)


def test_actual_match_rejects_incompatible_policy_before_playing():
    registry = baseline_registry()
    old = registry.resolve('batter', 'random')
    registry.register(PolicyEntry('bad', 'batter', old.policy,
                                  replace(old.metadata, action_schema='future-v9')))
    with pytest.raises(ValueError, match='Incompatible policy schema'):
        evaluate(engine(), MatchSpec('bad', 'random', 7, 1), registry=registry)


def test_new_policy_and_league_use_same_engine_and_recorder(tmp_path):
    registry = baseline_registry()
    baseline = registry.resolve('batter', 'random')
    registry.register(PolicyEntry('another_league_policy', 'batter', Batter('patient'),
                                  replace(baseline.metadata, training_league='another_synthetic_league')))
    c = config(batters=['another_league_policy'], profile={'league_id': 'neutral_synthetic'})
    payload = run_experiment(c, tmp_path, experiment_id='EXTENSION_TEST', test_only=True, registry=registry)
    assert payload['experiment_id'] == 'EXTENSION_TEST'
    assert payload['profile']['league_id'] == 'neutral_synthetic'
    assert payload['matches'][0]['policies']['batter']['training_league'] == 'another_synthetic_league'
    assert payload['summary'][0]['plate_appearances'] == 20


def test_validate_entire_tournament_before_writing(tmp_path):
    output = tmp_path/'invalid'
    with pytest.raises(ValueError, match='Unknown pitcher'):
        run_experiment(config(pitchers=['random', 'unregistered']), output, experiment_id='TEST', test_only=True)
    assert not output.exists()


def test_streamed_trace_can_reconstruct_results_and_metrics(tmp_path):
    payload = run_experiment(config(), tmp_path, experiment_id='TEST', test_only=True)
    with (tmp_path/'pitches.csv').open(newline='', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == sum(m['pitches'] for m in payload['matches'])
    for match in payload['matches']:
        matching = [row for row in rows if row['match_id'] == match['match_id']]
        assert len(matching) == match['pitches']
        terminals = [row for row in matching if row['result']]
        assert len(terminals) == match['match']['plate_appearances']
        for result, expected in match['results'].items():
            assert sum(row['result'] == result for row in terminals) == expected
        assert sum(row['batter_action'] == 'take' for row in matching) == match['action_counts']['take']
        for row in matching:
            assert row['schema_version'] == 'pitch-event-v1'
            assert row['league'] == 'synthetic_demo'
        for group in match['by_count'].values():
            assert sum(group['batter_actions'].values()) == group['pitches']
            assert sum(group['pitch_types'].values()) == group['pitches']
        for key in ('walk_rate', 'strikeout_rate', 'hit_rate'):
            metric = match['metrics'][key]
            assert 0 <= metric['ci95_wilson'][0] <= metric['value'] + 1e-12
            assert metric['value'] <= metric['ci95_wilson'][1] + 1e-12 <= 1 + 1e-12
    assert json.loads((tmp_path/'results.json').read_text(encoding='utf-8')) == payload
    assert 'EXTENSION_TEST' not in (tmp_path/'summary.md').read_text(encoding='utf-8')
    assert '매치업 행렬' in (tmp_path/'summary.md').read_text(encoding='utf-8')


def test_multiseed_reproducibility_and_no_trace_cleans_old_trace(tmp_path):
    raw = config().to_dict()
    raw['seeds'] = [5, 6, 7]
    c = ExperimentConfig.from_dict(raw)
    first = run_experiment(c, tmp_path, experiment_id='TEST', test_only=True)
    second = run_experiment(c, tmp_path, experiment_id='TEST', test_only=True, trace=False)
    assert first['matches'] == second['matches']
    assert len(first['matches']) == 6
    assert all(m['seeds'] == [5, 6, 7] for m in first['summary'])
    assert not (tmp_path/'pitches.csv').exists()


def test_same_pa_randomness_is_shared_across_matchups():
    a = evaluate(engine(), MatchSpec('random', 'random', 7, 40))
    b = evaluate(engine(), MatchSpec('random', 'mixed', 7, 40))
    assert a['first_pitch_swing_rate'] == b['first_pitch_swing_rate']


@pytest.mark.parametrize('value', [-1, 1.5, True, float('inf')])
def test_invalid_counts_and_thresholds(value):
    with pytest.raises(ValueError):
        RuleSet(balls_to_walk=value)
    with pytest.raises(ValueError):
        transition(State(value, 0), 'ball', RuleSet())


@pytest.mark.parametrize('ability', [0.0, 0.5, 1.0])
def test_abilities_have_valid_distributions_and_affect_outcomes(ability):
    from baseball_lab.core.contracts import PITCH_ACTIONS
    model = SyntheticOutcome()
    ctx = OutcomeContext(Observation(0, 0), PlayerAttributes(ability, ability, ability))
    for pitch in PITCH_ACTIONS:
        for bat in BatAction:
            distribution = model.probabilities(pitch, bat, context=ctx)
            assert sum(distribution.values()) == pytest.approx(1)
            assert all(0 <= value <= 1 for value in distribution.values())
    high = OutcomeContext(Observation(0, 0), PlayerAttributes(contact=1))
    low = OutcomeContext(Observation(0, 0), PlayerAttributes(contact=0))
    pitch = PitchAction('fastball', True)
    assert model.probabilities(pitch, BatAction.CONTACT, context=high)['strike'] < model.probabilities(pitch, BatAction.CONTACT, context=low)['strike']


def test_model_receives_context_without_policy_leak():
    class ContextModel:
        calibration_id = 'synthetic-v1'
        def sample(self, pitch, bat, rng, *, context):
            assert context.attributes.contact == 0.75
            assert isinstance(context.observation, Observation)
            return 'out'
    class PublicPolicy:
        def act(self, obs, legal, rng):
            assert set(vars(obs)) == {'balls', 'strikes'}
            return legal[0]
    e = Engine(RuleSet(), LeagueProfile(), ContextModel(), PlayerAttributes(contact=.75))
    state, _ = e.play(PublicPolicy(), PublicPolicy(), Random(1), Random(2), Random(3))
    assert state.result == 'out'


def test_raw_string_action_is_rejected_at_engine_boundary():
    class Bad:
        def act(self, observation, legal, rng):
            return 'take'
    with pytest.raises(ValueError, match='Illegal action'):
        engine().play(Bad(), Bad(), Random(1), Random(2), Random(3))


def test_cli_from_another_directory_requires_real_data(tmp_path):
    cmd = [sys.executable, str(ROOT/'scripts/quickstart.py')]
    result = subprocess.run([*cmd, '--data-dir',str(tmp_path/'absent'),'--output',str(tmp_path/'run')],
                            cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'})
    assert result.returncode == 2
    payload=json.loads((tmp_path/'run/report-data.json').read_text(encoding='utf-8'))
    assert payload['status']=='DATA_REQUIRED' and payload['observed']==[] and payload['replays']==[]
    assert not (tmp_path/'run/checkpoints').exists()


def test_git_optional_for_result_tracking(tmp_path):
    with patch('baseball_lab.tracking.results.subprocess.run', side_effect=FileNotFoundError):
        identity = code_identity(tmp_path)
    assert identity['code_revision'] == 'unavailable'
    assert identity['working_tree_dirty'] is None
    assert len(identity['code_sha256']) == 64


def test_failed_simulation_preserves_previous_complete_run(tmp_path):
    class Broken:
        calibration_id = 'synthetic-v1'
        def sample(self, pitch, bat, rng, *, context):
            raise RuntimeError('broken model')
    output = tmp_path/'results'
    run_experiment(config(), output, experiment_id='TEST', test_only=True)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(RuntimeError, match='broken model'):
        run_experiment(config(), output, experiment_id='TEST', test_only=True, outcome=Broken())
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}
    assert list(tmp_path.iterdir()) == [output]
