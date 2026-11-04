from dataclasses import replace
from random import Random
import json
import math
import pytest
from baseball_lab.core.contracts import *
from baseball_lab.core.engine import Engine, State, transition
from baseball_lab.outcome.synthetic import SyntheticOutcome
from baseball_lab.agents.baselines import Batter, Pitcher, BATTERS, PITCHERS
from baseball_lab.agents.metadata import PolicyMetadata
from baseball_lab.evaluation.matches import MatchSpec, evaluate
from baseball_lab.tracking.results import save


def engine(profile=LeagueProfile(), rules=RuleSet()):
    return Engine(rules, profile, SyntheticOutcome())


def test_walk_strikeout_and_two_strike_foul():
    rules = RuleSet()
    state = State()
    for _ in range(4):
        state = transition(state, 'ball', rules)
    assert state.result == 'walk'
    state = transition(State(2, 2), 'foul', rules)
    assert state == State(2, 2)
    assert transition(state, 'strike', rules).result == 'strikeout'
    with pytest.raises(ValueError):
        transition(State(result='walk'), 'ball', rules)
    with pytest.raises(ValueError):
        transition(State(), 'invented', rules)


@pytest.mark.parametrize('result', ['out', 'single', 'double', 'triple', 'home_run'])
def test_in_play_ends_plate_appearance(result):
    assert transition(State(), result, RuleSet()).result == result


@pytest.mark.parametrize('pitch', PITCH_ACTIONS)
@pytest.mark.parametrize('bat', tuple(BatAction))
def test_probability_distribution(pitch, bat):
    p = SyntheticOutcome().probabilities(pitch, bat)
    assert math.isclose(sum(p.values()), 1)
    assert all(math.isfinite(v) and 0 <= v <= 1 for v in p.values())


@pytest.mark.parametrize('batter', BATTERS)
@pytest.mark.parametrize('pitcher', PITCHERS)
def test_reproducible_complete_matches(batter, pitcher):
    spec = MatchSpec(batter, pitcher, 123, 100)
    a = evaluate(engine(), spec)
    assert a == evaluate(engine(), spec)
    assert sum(a['results'].values()) == 100
    assert sum(a['action_counts'].values()) == a['pitches']
    assert sum(a['pitch_type_counts'].values()) == a['pitches']
    assert sum(a['count_action_counts'].values()) == a['pitches']
    assert math.isclose(sum(a['action_rates'].values()), 1)


def test_seed_changes_trajectory():
    assert evaluate(engine(), MatchSpec('random', 'random', 1, 100)) != evaluate(engine(), MatchSpec('random', 'random', 2, 100))


def test_profile_and_rules_injection():
    profile = replace(LeagueProfile(), league_id='alternate_synthetic', ruleset_id='short')
    rules = RuleSet('short', 2, 2)
    e = engine(profile, rules)
    assert transition(State(1, 0), 'ball', e.rules).result == 'walk'
    assert sum(evaluate(e, MatchSpec('patient', 'mixed', 3, 50))['results'].values()) == 50
    for bad in [replace(profile, ruleset_id='wrong'), replace(profile, calibration_id='wrong'), replace(profile, feature_schema_version='wrong')]:
        with pytest.raises(ValueError):
            engine(bad, rules)


def test_observation_no_current_pitch_and_illegal_action():
    class Spy:
        def act(self, obs, legal, rng):
            assert set(vars(obs)) == {'balls', 'strikes'}
            return legal[0]
    engine().play(Spy(), Spy(), Random(1), Random(2), Random(3))
    class Illegal:
        def act(self, obs, legal, rng):
            return 'teleport'
    with pytest.raises(ValueError, match='Illegal action'):
        engine().play(Illegal(), Pitcher('random'), Random(1), Random(2), Random(3))


def test_schema_rejection():
    meta = PolicyMetadata('v1', OBSERVATION_SCHEMA, ACTION_SCHEMA, 'none', 'basic', 'synthetic', 'none', 'baseline', 1, 'unborn')
    meta.validate_compatibility()
    with pytest.raises(ValueError, match='adapter'):
        replace(meta, action_schema='future').validate_compatibility()


def test_safety_limit_is_not_a_result():
    class Fouls:
        calibration_id = 'synthetic-v1'
        def sample(self, pitch, bat, rng):
            return 'foul'
    e = Engine(RuleSet(), LeagueProfile(), Fouls())
    with pytest.raises(RuntimeError, match='safety limit'):
        e.play(Batter('random'), Pitcher('random'), Random(1), Random(2), Random(3), max_pitches=5)


def test_saved_results(tmp_path):
    matches = [evaluate(engine(), MatchSpec('random', 'mixed', 5, 10))]
    save(tmp_path, LeagueProfile(), RuleSet(), matches, {'seed': 5})
    payload = json.loads((tmp_path/'results.json').read_text())
    assert payload['trained'] is False
    assert payload['matches'] == matches
    assert len((tmp_path/'matchups.csv').read_text().splitlines()) == 2
