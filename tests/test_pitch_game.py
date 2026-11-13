"""MOCK_TEST_ONLY pitch action semantics, valid counts and decision boundaries."""
from random import Random
import numpy as np
import pytest
from baseball_lab.experiments.match.pitch_game.research import sequence,policy,Observation,OFF,DEF,play,finish


def turn(pitches,event):return {'pitches':pitches,'event':event,'intentional_walk':False}


def test_pitch_actions_are_observed_swing_or_take_not_outcome_categories():
    rows=sequence(turn('BBCSFFS','strikeout'))
    assert [r[2] for r in rows]==['take','take','take','swing','swing','swing','swing']
    assert rows[-1][:2]==(2,2) and rows[-1][3]=='strike'
    assert sequence(turn('BBBCB','walk'))[-1][:2]==(3,1)
    assert sequence(turn('CX','home_run'))[-1][3]=='home_run'
    assert not sequence(turn('SXS','single')) and not sequence(turn('VBBCCB','walk'))


def test_neural_agent_cannot_choose_a_result_or_a_donor_record():
    b=policy('batter',41);p=policy('pitcher',42)
    assert b.actions==OFF and p.actions==DEF
    assert not {'single','home_run','early_swing','ordinary_turn'}&set(b.actions)
    with pytest.raises(ValueError):b.act(Observation(1,0,0,0,0,0,0,0,0),['home_run'],Random(1))


def test_score_orientation_for_alternating_home_teams():
    assert finish([0,1],[],[{},{}],(1,0))['winner']==0
    assert finish([0,1],[],[{},{}],(1,0))['scores']==[1,0]


class Take:
    def act(self,o,legal,rng):return 'take'
class Management:
    def __init__(self):self.seen=[]
    def act(self,o,legal,rng):
        self.seen.append((o,legal))
        return next((x for x in legal if x.startswith('change_')),'pitch')
class StrikeWorld:
    pitchers=['MOCK_TEST_ONLY_0','MOCK_TEST_ONLY_1','MOCK_TEST_ONLY_2']
    def pitch(self,*args):return 'strike'
    def advance(self,outs,bases,event,rng):assert event=='strikeout';return outs+1,bases,0


def test_count_progresses_and_pitcher_cannot_reenter_or_change_before_three_batters():
    a=Management();b=Management()
    with pytest.raises(RuntimeError,match='18회 동점'):play(StrikeWorld(),[(Take(),a),(Take(),b)],41)
    assert any(o.strikes==2 for o,legal in a.seen)
    # After replacing the starter, both bench pitchers cannot be used immediately.
    assert any(o.pitcher==1 and o.faced==0 and not any(x.startswith('change_') for x in legal) for o,legal in a.seen)
    assert all('change_0' not in legal for o,legal in a.seen)


def test_learned_world_masks_impossible_actions_without_sampling_history_rows():
    from baseball_lab.experiments.match.pitch_game.research import World,EVENTS
    w=World.__new__(World);w.pitchers=['MOCK_TEST_ONLY_0','MOCK_TEST_ONLY_1','MOCK_TEST_ONLY_2']
    w.supported={'take':{'ball','strike','hbp'},'swing':{'strike','foul','out','home_run'}}
    w.w=np.zeros((17,len(EVENTS)))
    assert not hasattr(w,'records') and not hasattr(w,'donors')
    for action in OFF:
        events={w.pitch(1,1,action,w.pitchers[0],Random(i)) for i in range(100)}
        assert events<=w.supported[action]
    assert 'home_run' not in {w.pitch(1,1,'take',w.pitchers[0],Random(i)) for i in range(100)}
