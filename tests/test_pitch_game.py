"""MOCK_TEST_ONLY pitch action semantics, valid counts and decision boundaries."""
from random import Random
import numpy as np
import pytest
from baseball_lab.experiments.match.pitch_game.research import sequence,policy,Observation,OFF,PITCH_OFF,DEF,play,finish,World


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
    def legal(self,o):return ('take','swing')
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
    from collections import Counter,defaultdict
    from baseball_lab.experiments.match.pitch_game.research import World,EVENTS
    w=World.__new__(World);w.pitchers=['MOCK_TEST_ONLY_0','MOCK_TEST_ONLY_1','MOCK_TEST_ONLY_2']
    w.supported={'take':{'ball','strike','hbp'},'swing':{'strike','foul','out','home_run'},'bunt':{'strike','bunt_foul','out','single'}}
    w.baseline=defaultdict(Counter)
    w.pooled={a:Counter({e:1 for e in events}) for a,events in w.supported.items()}
    w.selected_iterations=100
    w.w=np.zeros((17,len(EVENTS)))
    assert not hasattr(w,'records') and not hasattr(w,'donors')
    for action in PITCH_OFF:
        events={w.pitch(1,1,action,w.pitchers[0],Random(i)) for i in range(100)}
        assert events<=w.supported[action]
    assert 'home_run' not in {w.pitch(1,1,'take',w.pitchers[0],Random(i)) for i in range(100)}


def test_management_does_not_train_unexecuted_batter_decisions():
    class CountTake:
        calls=0
        def act(self,o,legal,rng):
            self.calls+=1
            return 'take'
    class Manage(Management):
        walks=0
        def act(self,o,legal,rng):
            action=super().act(o,legal,rng)
            if action=='pitch' and self.walks==0:
                self.walks+=1
                return 'intentional_walk'
            return action
    class CountWorld(StrikeWorld):
        pitches=0
        def pitch(self,*args):
            self.pitches+=1
            return 'strike'
        def advance(self,outs,bases,event,rng):
            if event=='walk':return outs,1,0
            return super().advance(outs,bases,event,rng)
    world=CountWorld();batters=[CountTake(),CountTake()];defense=[Manage(),Manage()]
    with pytest.raises(RuntimeError,match='18회 동점'):
        play(world,[(batters[i],defense[i]) for i in (0,1)],41)
    assert sum(b.calls for b in batters)==world.pitches
    assert sum(len(d.seen) for d in defense)>world.pitches
    assert all(d.walks==1 for d in defense)


def mock_pitch_dataset():
    rows=[]
    for day in range(1,11):
        for i in range(160):
            pitches,event=(('BBBB','walk'),('CCC','strikeout'),('CX','single'),('CX','out'))[i%4]
            rows.append({'date':f'2000-04-{day:02d}','pitcher':f'MOCK_TEST_ONLY_{i%3}',
                'pitches':pitches,'event':event,'intentional_walk':False,'outs':0,'bases':0,
                'outs_added':int(event in ('strikeout','out')),'end_bases':int(event in ('single','walk')),'runs':0})
        # Valid movement but uninterpretable pitch sequence, retained for runners.
        rows.append({**rows[-1],'pitches':'U','event':'single','outs_added':0,'end_bases':1})
    return {'pitch_turns':rows,'manifest':{'dataset_id':'MOCK_TEST_ONLY'}}


def test_world_selection_never_uses_final_test_and_keeps_valid_runner_evidence():
    from copy import deepcopy
    data=mock_pitch_dataset();world=World(data)
    altered=deepcopy(data)
    for row in altered['pitch_turns']:
        if row['date']>='2000-04-09':
            row.update(pitches='BBBB',event='walk',outs_added=0,end_bases=1)
    other=World(altered)
    assert np.array_equal(world.w,other.w)
    assert world.selected_iterations==other.selected_iterations
    assert world.metrics['validation']==other.metrics['validation']
    assert world.metrics['test']!=other.metrics['test']
    assert world.metrics['validation']['brier']<=world.metrics['validation']['baseline_brier']+1e-12
    assert world.evidence['runner_fit_turns']==6*161
    assert world.runner[0,0,'single',False][0,1,0]==6*41
    for counts in world.evidence['coverage'].values():
        assert counts['source_turns']==counts['used_turns']+sum(counts['excluded_by_reason'].values())
        assert counts['excluded_by_reason']['unsupported_pitch_code']>0


def test_evaluation_does_not_change_or_collect_policy_parameters(monkeypatch):
    from baseball_lab.experiments.match.pitch_game import research
    teams=[(policy('batter',i*2),policy('pitcher',i*2+1)) for i in (0,1)]
    before=[[a.state_dict() for a in team] for team in teams];homes=[]
    def game(world,pair,seed,home_team):
        homes.append(home_team)
        assert all(not a.collect for team in pair for a in team)
        return {'winner':home_team}
    monkeypatch.setattr(research,'play',game)
    result=research.evaluate(None,teams,20,41)
    assert result=={'games':20,'wins':[10,10]}
    assert homes==[0,1]*10
    assert before==[[a.state_dict() for a in team] for team in teams]
