"""MOCK_TEST_ONLY synthetic cases stay in tests; packaged records remain real."""
from copy import deepcopy
from random import Random
import pytest
from baseball_lab.data.batting_directions import handedness,approach,retro_area,narrative_area,contact_type
from baseball_lab.experiments.match.pitch_game.corpus_world import CorpusWorld,Observation
from baseball_lab.experiments.match.pitch_game.directional_contact import ContactModel,directions
from baseball_lab.experiments.match.pitch_game import strategy


@pytest.fixture(scope='module')
def world():return CorpusWorld()


def test_left_right_is_relative_to_known_batting_stance_not_pitcher_hand():
    assert approach('left','R')=='pull' and approach('right','R')=='opposite'
    assert approach('left','L')=='opposite' and approach('right','L')=='pull'
    assert handedness('switch')=='U' and handedness('B')=='U'
    assert approach('left','U')=='left' and approach(None,'L') is None
    assert retro_area('7D+')=='left' and retro_area('34D+')=='right'
    assert retro_area('78XD') is None and retro_area('?') is None
    assert narrative_area('MOCK_TEST_ONLY : 좌익수 앞 1루타','KBO')=='left'
    assert narrative_area('MOCK_TEST_ONLY ライトへのヒット','NPB')=='right'
    assert contact_type('MOCK_TEST_ONLY 좌익수 뒤 홈런','home_run') is None
    assert contact_type('MOCK_TEST_ONLY 땅볼 아웃','out')=='ground'


def test_packaged_contacts_match_all44_cohorts_and_keep_unknowns(world):
    data=directions()
    assert data['source_status']=='REAL_OBSERVED' and set(data['cohorts'])==set(world.cohorts)
    assert sum(c['coverage']['fit']['contact_rows'] for c in data['cohorts'].values())==2074209
    assert any(c['coverage']['fit'].get('area_unknown',0)>0 for c in data['cohorts'].values())
    assert any(c['hand_counts']['fit'].get('U',0)>0 for c in data['cohorts'].values())
    for k,c in data['cohorts'].items():assert c['split']==world.cohorts[k].value['split']


def test_future_contacts_do_not_select_models_or_open_actions(world):
    model=next(m for m in world.contacts.values() if m.value['counts']['test'])
    altered=deepcopy(model.value)
    for row in altered['counts']['test']:row[-1]*=9
    other=ContactModel(altered)
    assert model.strength==other.strength
    assert model.legal(0,0,'R')==other.legal(0,0,'R')
    assert model.outcomes(0,0,'R','pull')==other.outcomes(0,0,'R','pull')


def test_direction_target_preserves_observed_miss_and_foul_chances(world):
    key=next(k for k in world.cohorts if k.startswith('MLB:2019:'))
    world.requested_context=key;world.begin_game(0);world.bat_hand='R'
    o=Observation(1,0,0,0,0,0,0,0,0,'MLB',2019,bat_hand='R')
    world.prepare(o,'pitch',Random(3));base=world.pitch_probabilities(0,0,'swing')
    for action in ('swing:pull','swing:center','swing:opposite'):
        assert action in world.legal(o)
        q=world.pitch_probabilities(0,0,action)
        assert sum(q.values())==pytest.approx(1.) and min(q.values())>=0
        for event in ('ball','strike','foul','bunt_foul','hbp'):assert q[event]==base[event]
        assert q['strike']+q['foul']>0  # A target never guarantees contact or a hit.
    seen=set()
    for _ in range(100):
        event=world.deliver(0,0,'swing:pull',world.pitchers[0],'pitch',Random(_))
        if world.last_contact:seen.add(world.last_contact['side'])
    assert seen=={'left'}


def test_unknown_stance_uses_field_targets_without_claiming_pull_or_opposite(world):
    key=next(k for k in world.cohorts if k.startswith('NPB:2019:'))
    world.requested_context=key;world.begin_game(0)
    o=Observation(1,0,0,0,0,0,0,0,0,'NPB',2019,bat_hand='U')
    legal=world.legal(o)
    assert 'swing:left' in legal and 'swing:right' in legal
    assert 'swing:pull' not in legal and 'swing:opposite' not in legal


def test_telemetry_counts_only_executed_decisions_and_keeps_unknown_direction():
    stats=strategy.new_stats();o=Observation(1,0,0,0,0,0,0,0,0)
    strategy.observe(stats,0,'intentional_walk',None,'walk',('take','swing'),('pitch','intentional_walk'),o,None,'MOCK_TEST_ONLY')
    assert not stats[0]['offense'] and not stats[0]['opportunities']['offense']
    strategy.observe(stats,0,'pitch','swing','out',('take','swing'),('pitch',),o,None,'MOCK_TEST_ONLY')
    assert stats[0]['offense']=={'swing':1}
    assert stats[0]['opportunities']['offense']=={'take':1,'swing':1}
    assert stats[0]['batted_area']=={'unknown':1}
    assert stats[1]['defense']=={'intentional_walk':1,'pitch':1}


def test_fixed_state_preferences_do_not_change_policy_weights(world):
    teams=[world.new_team(41),world.new_team(43)]
    before=[[a.state_dict() for a in t] for t in teams]
    probes=world.strategy_probes(teams)
    assert {p['context']['environment'] for p in probes}==set(world.cohorts)
    assert probes and all(p['context']['hand'] in ('L','R','U') for p in probes)
    assert before==[[a.state_dict() for a in t] for t in teams]
    assert all(sum(p['teams'][i][role].values())==pytest.approx(1.) for p in probes for i in (0,1) for role in ('offense','defense'))
