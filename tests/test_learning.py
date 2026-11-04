"""Game-rule boundaries, exact policy-gradient checks and actual training integration."""
import json
from dataclasses import replace
from pathlib import Path
from random import Random

import numpy as np
import pytest

from baseball_lab.agents.game_baselines import GameBaseline
from baseball_lab.agents.neural import NeuralPolicy, features
from baseball_lab.core.contracts import LeagueProfile
from baseball_lab.core.game import (GameEngine, GameRules, GameObservation, Team, BAT_PLAYS,
                                     PITCH_PLAYS, BatPlay, PitchPlay, advance, GAME_OBSERVATION_SCHEMA)
from baseball_lab.outcome.game import GameOutcome
from baseball_lab.training.self_play import TrainingConfig, train, load_checkpoint
from baseball_lab.training.replay import replay_checkpoint


def obs(**kwargs):
    defaults = dict(balls=0, strikes=0, inning=1, regulation_innings=3, outs=0,
                    bases=(False, False, False), batting_score=0, fielding_score=0, bottom=False, pitcher_load=0.)
    return GameObservation(**(defaults | kwargs))


def team(style='random'):
    return Team(style, GameBaseline('batter', style), GameBaseline('pitcher', 'random'))


@pytest.mark.parametrize('bases,expected,run', [
    ((False,False,True), (True,False,True), 0),
    ((True,False,True), (True,True,True), 0),
    ((False,True,True), (True,True,True), 0),
    ((True,True,True), (True,True,True), 1),
])
def test_forced_walk(bases, expected, run):
    assert advance(bases, 'walk', 0, Random(0)) == (expected,run,0)


def test_home_run_and_sacrifice_and_third_out():
    assert advance((True,True,True),'home_run',0,Random(0)) == ((False,False,False),4,0)
    assert advance((True,False,True),'bunt_out',0,Random(0)) == ((False,True,False),1,1)
    assert advance((True,False,True),'bunt_out',2,Random(0)) == ((True,False,True),0,1)
    assert advance((True,False,True),'ground_out',1,Random(1)) == ((False,False,True),0,2)


def test_bunt_foul_at_two_strikes_is_third_strike():
    class RNG:
        def random(self):
            return .05
    assert GameOutcome().sample(obs(strikes=2),PitchPlay('fastball',True,0),BatPlay.BUNT,RNG()) == 'strike'
    assert GameOutcome().sample(obs(strikes=1),PitchPlay('fastball',True,0),BatPlay.BUNT,RNG()) == 'foul'


def test_tie_is_zero_reward_without_fabricated_winner():
    class AlwaysOut:
        calibration_id='test'
        def sample(self,*args): return 'out'
    result = GameEngine(AlwaysOut(),GameRules(1,1)).play(team(),team(),1,record=True)
    assert result.winner is None and result.reward(0) == result.reward(1) == 0
    assert result.innings_played == 2
    assert result.pitches == 12


def test_walkoff_and_skipped_bottom():
    class HomeWins:
        calibration_id='test'
        def sample(self,obs,*args): return 'home_run' if obs.bottom and obs.batting_score == 0 else 'out'
    result = GameEngine(HomeWins(),GameRules(1)).play(team(),team(),0,record=True)
    assert result.home_score == 1 and result.away_score == 0 and len(result.events) == 4
    result = GameEngine(HomeWins(),GameRules(2)).play(team(),team(),0,record=True)
    assert result.home_score == 1 and result.pitches == 10
    assert not any(e["inning"] == 2 and e["bottom"] for e in result.events)


def test_game_reproducibility_nine_innings_and_public_observation():
    class Spy:
        def __init__(self,role): self.role=role
        def act(self,observation,legal,rng):
            assert isinstance(observation,GameObservation)
            assert 'pitch_type' not in vars(observation) and 'target_zone' not in vars(observation)
            assert 0 <= observation.outs < 3 and 0 <= observation.balls < 4 and 0 <= observation.strikes < 3
            return rng.choice(legal)
    spy=Team('public',Spy('batter'),Spy('pitcher'))
    engine=GameEngine(GameOutcome(),GameRules(9))
    a=engine.play(spy,spy,32,record=True)
    b=engine.play(spy,spy,32,record=True)
    assert a == b
    assert 9 <= a.innings_played <= 11
    assert a.reward(0) == -a.reward(1)
    assert a.pitches == len(a.events)
    for row in a.events:
        assert sum(row['bases_after']) <= 3 and 0 <= row['outs_after'] <= 3
        assert row['runs'] >= 0


def test_game_profile_and_illegal_actions():
    profile=LeagueProfile(feature_schema_version=GAME_OBSERVATION_SCHEMA,calibration_id='synthetic-game-v1')
    GameEngine(GameOutcome(),profile=profile)
    with pytest.raises(ValueError,match='Incompatible'):
        GameEngine(GameOutcome(),profile=replace(profile,calibration_id='unknown'))
    class Bad:
        def act(self,*args): return 'bunt'
    with pytest.raises(ValueError,match='Illegal'):
        GameEngine(GameOutcome()).play(Team('bad',Bad(),Bad()),team(),1)


def test_safety_bound_does_not_invent_a_result_or_reward():
    class Hits:
        calibration_id='test'
        def sample(self,*args): return 'single'
    with pytest.raises(RuntimeError,match='safety limit'):
        GameEngine(Hits(),GameRules(3,max_plate_appearances_per_half=3)).play(team(),team(),1)


def test_neural_gradient_matches_finite_differences():
    policy=NeuralPolicy('batter',13,hidden=4)
    x=np.stack([features(obs(), 'batter'),features(obs(balls=2,strikes=1,bases=(True,False,False)),'batter')])
    acts=np.array([0,3]); advantage=np.array([1.,-.6])
    _,grads=policy.gradients(x,acts,advantage,2)
    epsilon=1e-5
    for param,grad in zip(policy.params,grads):
        index=tuple(0 for _ in param.shape)
        original=param[index]
        param[index]=original+epsilon
        plus=policy.gradients(x,acts,advantage,2)[0]
        param[index]=original-epsilon
        minus=policy.gradients(x,acts,advantage,2)[0]
        param[index]=original
        assert grad[index] == pytest.approx((plus-minus)/(2*epsilon),abs=1e-7)


def test_terminal_reward_updates_weights_without_stat_targets():
    p=NeuralPolicy('batter',12,hidden=8)
    x=features(obs(),'batter')
    before=p.probabilities(obs()).copy()
    p.update([([(x,3)],1.)],learning_rate=.01)
    assert p.probabilities(obs())[3] > before[3]
    zero=NeuralPolicy('batter',12,hidden=8)
    original=[v.copy() for v in zero.params]
    zero.update([([(x,3)],0.)])
    assert all(np.array_equal(a,b) for a,b in zip(original,zero.params))


def test_checkpoint_round_trip_and_rejection():
    p=NeuralPolicy('pitcher',5,hidden=8)
    restored=NeuralPolicy.from_state_dict(p.state_dict())
    assert np.array_equal(p.probabilities(obs()),restored.probabilities(obs()))
    data=p.state_dict();data['action_schema']='wrong'
    with pytest.raises(ValueError,match='Incompatible'):
        NeuralPolicy.from_state_dict(data)
    data=p.state_dict();data['parameters'][0][0][0]=float('nan')
    with pytest.raises(ValueError,match='Invalid'):
        NeuralPolicy.from_state_dict(data)


def test_actual_training_and_replay_are_reproducible(tmp_path):
    config=TrainingConfig(games=24,innings=1,evaluate_every=8,evaluation_pairs=2,batch_size=4,hidden=8,seed=71)
    a=train(config,tmp_path/'a',progress=lambda *args: None, experiment_id='TRAIN_TEST', test_only=True)
    b=train(config,tmp_path/'b',progress=lambda *args: None, experiment_id='TRAIN_TEST', test_only=True)
    assert a['history'] == b['history']
    assert a['reward'] == {'win':1,'loss':-1,'draw':0,'intermediate':0}
    assert [e['games'] for e in a['history']] == [0,8,16,24]
    assert sum(a['history'][-1]['opponents_seen'].values()) == 24
    checkpoint=tmp_path/'a/checkpoints/game_000024.json'
    learned,_,metadata=load_checkpoint(checkpoint)
    initial,_,_=load_checkpoint(tmp_path/'a/checkpoints/game_000000.json')
    for role in ('batter','pitcher'):
        assert any(not np.array_equal(x,y) for x,y in zip(getattr(learned,role).params,getattr(initial,role).params))
    before=checkpoint.read_bytes()
    evaluated=replay_checkpoint(checkpoint,tmp_path/'replay',pairs=2, test_only=True)
    assert before == checkpoint.read_bytes()
    assert evaluated['training_executed'] is False
    assert evaluated['history'][0]['evaluation'] == a['history'][-1]['evaluation'][:3]
    assert (tmp_path/'a/report.html').exists() and (tmp_path/'replay/report.html').exists()
    assert (tmp_path/'a/summary.md').read_text(encoding='utf-8').startswith('# 타자·투수')
    with pytest.raises(ValueError,match='기존 학습 결과'):
        train(config,tmp_path/'a',progress=lambda *args: None, experiment_id='TRAIN_TEST', test_only=True)


def test_legacy_synthetic_learning_cannot_run_as_research(tmp_path):
    with pytest.raises(ValueError,match='단위 테스트 전용'):
        train(TrainingConfig(games=8),tmp_path/'denied',experiment_id='E01')
    assert not (tmp_path/'denied').exists()
