"""MOCK_TEST_ONLY deterministic rule tests; no synthetic records enter research."""
from collections import defaultdict
from random import Random
import numpy as np
import pytest
from baseball_lab.r1.environment import Observation
from baseball_lab.experiments.match.full_game.research import Environment,Situation,policy,OFF,DEF

class Base:
    def step(self,o,b,p,rng):
        return Observation(o.outs+1,0),int(b=='bunt_attempt'),{'source_status':'MOCK_TEST_ONLY'}
class Agent:
    def __init__(self,kind='ordinary_turn',inning=1):self.kind=kind;self.inning=inning
    def act(self,o,legal,rng):return self.kind if o.inning>=self.inning and self.kind in legal else legal[0]

def env():return Environment(Base(),[],[],{(o,b):('ordinary_turn','bunt_attempt') for o in range(3) for b in range(8)})
def team(kind='ordinary_turn',inning=1):return Agent(kind,inning),Agent('challenge')


def test_home_lead_skips_bottom_ninth_and_reward_is_terminal_win():
    r=env().game(team('bunt_attempt'),team(),41,home=True,record=True)
    assert r['reward']==1 and r['innings']==9 and len(r['events'])==51
    assert r['events'][-1]['bottom']==0
    assert r['home']==24 and r['away']==0


def test_home_behind_plays_bottom_ninth_and_away_wins():
    r=env().game(team('bunt_attempt'),team(),41,home=False,record=True)
    assert r['reward']==1 and r['innings']==9 and len(r['events'])==54
    assert r['events'][-1]['bottom']==1 and r['away']==27 and r['home']==0


def test_walkoff_ends_mid_inning_and_extras_place_runner_on_second():
    r=env().game(team('bunt_attempt',9),team(),41,home=True,record=True)
    assert r['innings']==9 and r['home']==1 and r['events'][-1]['after']['outs']==1
    r=env().game(team('bunt_attempt',10),team(),41,home=True,record=True)
    extra=[e for e in r['events'] if e['inning']==10 and e['before']['outs']==0]
    assert len(extra)==2 and all(e['before']['bases']==2 for e in extra)


def test_safety_limit_never_makes_up_a_winner():
    with pytest.raises(RuntimeError,match='18회까지 동점'):env().game(team(),team(),41)


def test_policy_observes_score_inning_role_and_checkpoint_updates():
    b=policy('batter',41);p=policy('pitcher',42)
    o=Situation(9,1,1,1,-1)
    assert set(b.actions)==set(OFF) and set(p.actions)==set(DEF)
    assert not np.array_equal(b.encoder(o,'batter'),b.encoder(Situation(1,0,1,1,0),'batter'))
    before=[x.copy() for x in b.params];b.collect=True
    for _ in range(8):b.act(o,OFF,Random(41))
    b.update([(b.decisions,1)])
    assert any(not np.array_equal(x,y) for x,y in zip(before,b.params))


def test_multi_run_non_homer_walkoff_stops_at_winning_run():
    class Multi(Base):
        def step(self,o,b,p,rng):return Observation(o.outs+1,0),3 if b=='bunt_attempt' else 0,{'source_status':'MOCK_TEST_ONLY','donor_event_codes':['D']}
    e=Environment(Multi(),[],[],{(o,b):('ordinary_turn','bunt_attempt') for o in range(3) for b in range(8)})
    r=e.game(team('bunt_attempt',9),team(),41,home=True,record=True)
    assert r['home']==1


def test_home_run_walkoff_credits_all_runs():
    class Homer(Base):
        def step(self,o,b,p,rng):return Observation(o.outs+1,0),3 if b=='bunt_attempt' else 0,{'source_status':'MOCK_TEST_ONLY','donor_event_codes':['HR']}
    e=Environment(Homer(),[],[],{(o,b):('ordinary_turn','bunt_attempt') for o in range(3) for b in range(8)})
    assert e.game(team('bunt_attempt',9),team(),41,home=True)['home']==3
