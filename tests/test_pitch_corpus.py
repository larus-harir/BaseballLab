"""MOCK_TEST_ONLY observations: source semantics, leakage, units and movement."""
import pytest
from baseball_lab.data.pitch_normalize import kbo,npb,metric_zone,final_event
from baseball_lab.data.pitch_corpus import transition_between


def kbo_row(**kw):
    return {'game_id':'MOCK_TEST_ONLY_game','inning':'1','home_or_away':'0','score_diff':'0',
        'out_count':'0','ball_count_B':'1','ball_count_S':'0','is_base1':'0','is_base2':'0','is_base3':'0',
        'pitcher_id':'MOCK_TEST_ONLY_pitcher','batter_id':'MOCK_TEST_ONLY_batter','pitch_speed':'144',
        'pitch_type':'직구','pitch_result':'B','relay_text':'MOCK_TEST_ONLY 타자 : 홈런',**kw}


def test_kbo_post_counts_are_reversed_and_future_relay_is_not_an_input():
    r=kbo(kbo_row(),None,2,{'is_regular_season':'True','date':'2016-04-01'})
    assert (r['balls'],r['strikes'],r['event'],r['terminal'])==(0,0,'ball',None)
    assert r['speed_mps']==40 and r['location'] is None
    assert 'relay_text' not in r and 'reward_wpa' not in r
    final=kbo(kbo_row(pitch_result='H',ball_count_B='0'),None,3,{'is_regular_season':'True','date':'2016-04-01'})
    assert final['terminal']=='home_run'


def test_double_play_is_not_a_double_and_terminal_label_is_not_leaked():
    for text in ('Double Play','Triple Play','Grounded Into DP','Sac Bunt','MOCK_TEST_ONLY 유격수 병살타'):
        assert final_event(text)=='out'
    assert final_event('Double')=='double'
    assert final_event('Bunt Single')=='single'


def test_two_strike_foul_does_not_invent_pre_pitch_count():
    row=kbo_row(pitch_result='F',ball_count_B='0',ball_count_S='2')
    with pytest.raises(ValueError,match='count'):kbo(row,None,2,{'is_regular_season':'True','date':'2016-04-01'})
    previous={**row,'pitch_result':'S'}
    r=kbo(row,previous,3,{'is_regular_season':'True','date':'2016-04-01'})
    assert r['strikes']==2


def test_npb_pixels_are_not_converted_into_mlb_physical_coordinates():
    row={'game_type_id':'1','game_type_name':'セ・リーグ公式戦','pitch_number':'1.0','pitch_id':'31.0',
        'description_jap':'1球目:外角低めのストレートを見送ってボール 1-0','presult':'118.0',
        'game_state_name':'1回表','release_speed_kmh':'144','plate_x':'100','plate_y':'180',
        'game_date':'2025-04-01 18:00:00+09:00','game_id':'MOCK_TEST_ONLY_game','fiveDigitSerialNumber':'1101',
        'inning':'1','balls':'0','strikes':'0','outs_when_up':'0','pitcher':'MOCK_TEST_ONLY_p','batter':'MOCK_TEST_ONLY_b','addedRuns':'0'}
    r=npb(row)
    assert r['pitch_family']=='fastball' and r['location']=='outside_low'
    assert r['speed_mps']==40 and r['x_m'] is None and r['z_m'] is None
    assert (r['raw_x'],r['raw_z'])==(100,180)
    assert r['coordinate_system']=='SPAIA_display_pixels_unverified'
    assert metric_zone(-.5,3.5,1.5,3.5,'R')=='inside_high'
    assert metric_zone(-.5,3.5,1.5,3.5,'L')=='outside_high'


def test_movements_require_observed_runs_and_valid_participant_conservation():
    before={'game':'MOCK_TEST_ONLY_game','terminal':'single','ordering':5,'inning':1,'bottom':0,'outs':0,
            'bases':1,'runs':None,'home_difference':0}
    after={'game':before['game'],'ordering':6,'inning':1,'bottom':0,'balls':0,'strikes':0,'outs':0,'bases':3,'home_difference':0}
    assert transition_between(before,after)==(0,3,0)
    assert transition_between({**before,'home_difference':None},after) is None
    assert transition_between(before,{**after,'bases':7}) is None
    assert transition_between(before,{**after,'balls':1}) is None
    assert transition_between(before,{**after,'inning':3}) is None
    assert transition_between(before,{**after,'sequence':3}) is None
    kbefore={**before,'game':'nextpitchh-naver-v1:MOCK_TEST_ONLY'}
    assert transition_between(kbefore,{**after,'game':kbefore['game'],'sequence':8,'ordering':8}) is None


@pytest.fixture(scope='module')
def world():
    from baseball_lab.experiments.match.pitch_game.corpus_world import CorpusWorld
    return CorpusWorld()


def test_verified_real_inventory_covers_all_collected_league_years(world):
    from baseball_lab.experiments.match.pitch_game.corpus_world import corpus,inventory
    data=corpus();rows=inventory()['cohorts']
    assert len(rows)==44
    assert {r['season'] for r in rows if r['league']=='MLB'}==set(range(2000,2026))
    assert {r['season'] for r in rows if r['league']=='KBO'}==set(range(2016,2026))
    assert {r['season'] for r in rows if r['league']=='NPB'}==set(range(2019,2027))
    assert data['source_status']=='REAL_OBSERVED'
    assert len(world.defense_actions)>200
    assert {'steal_2_3','steal_4'}<=set(world.offense_actions)
    assert any(row[3] is None for c in data['cohorts'].values() if c['source']!='retrosheet' for row in c['counts']['fit'])
    assert all(c.metrics['test']['pitches']>0 for c in world.cohorts.values())
    assert world.evidence['holdout_prediction']['test']['brier']<=world.evidence['holdout_prediction']['test']['baseline_brier']


def test_neutral_initial_policy_and_every_cohort_is_scheduled(world):
    import numpy as np
    from baseball_lab.experiments.match.pitch_game.corpus_world import Observation
    assert len({world.training_context(41,i) for i in range(1,45)})==44
    schedule=world.evaluation_contexts(20)
    assert len(schedule)==88 and all(schedule.count(k)==2 for k in world.cohorts)
    agents=world.new_team(41);world.begin_game(41)
    o=Observation(1,0,0,0,0,0,0,0,0,world.league,world.season)
    for a,legal in zip(agents,(world.legal(o),world.defense_legal(o))):
        p=a.probabilities(o,legal)
        assert np.allclose([p[a.actions.index(k)] for k in legal],1/len(legal))
        assert sum(p)==pytest.approx(1.)


def test_final_test_cannot_select_model_or_speed_quantiles(world):
    from copy import deepcopy
    from baseball_lab.experiments.match.pitch_game.corpus_world import Cohort
    from baseball_lab.data.corpus_measurements import cutpoints,band
    original=next(c for c in world.cohorts.values() if c.value['league']=='KBO')
    changed=deepcopy(original.value)
    for row in changed['counts']['test']:row[-1]={k:v*7 for k,v in row[-1].items()}
    assert Cohort(changed).strength==original.strength
    assert cutpoints({30:10,35:10,40:10})==[30,35]
    assert band(None,[30,35]) is None and band(35,[35,35])=='middle'
    assert band(29,[30,35])=='slow' and band(40,[30,35])=='fast'


def test_native_movements_support_all_ordinary_states_without_backwards_running(world):
    from baseball_lab.experiments.match.pitch_game.corpus_world import legal_movement
    for c in world.cohorts.values():
        for outs in range(3):
            for bases in range(8):
                for event in ('out','single','double','triple'):
                    counts,scope=c.movement(outs,bases,event)
                    assert counts and sum(counts.values())>0
                    assert all(legal_movement(outs,bases,event,*outcome) for outcome in counts)
    assert not legal_movement(0,4,'single',0,3,0)  # third-base runner cannot retreat to second
    assert not legal_movement(0,1,'double',0,3,0)  # batter cannot pass the existing runner


def test_joint_running_joins_explicit_narration_without_inventing_attempts():
    from baseball_lab.data.corpus_running import join
    before={'terminal':None,'event':'ball','observed_action':'take','balls':0,'strikes':0,'game':'MOCK_TEST_ONLY',
            'inning':1,'bottom':0,'bases':3,'pa':'MOCK_TEST_ONLY_pa','outs':0,'date':'2020-04-01'}
    after={**before,'balls':1,'bases':6}
    notes=['MOCK_TEST_ONLY 一塁走者 盗塁成功','MOCK_TEST_ONLY 二塁走者 盗塁成功']
    result=join(before,after,notes)
    assert result['action']=='steal_2_3' and (result['outs_added'],result['end_bases'],result['runs'])==(0,6,0)
    assert join(before,after,[]) is None
    assert join(before,{**after,'balls':2},notes) is None
    before={**before,'bases':4}
    result=join(before,{**after,'bases':0},['MOCK_TEST_ONLY 三塁走者 ホームスチール成功'])
    assert result['action']=='steal_4' and result['runs']==1


def test_pitch_source_paths_and_hosts_cannot_escape(tmp_path):
    from baseball_lab.data.pitch_sources import safe,member_path
    for url in ('http://raw.githubusercontent.com/a','https://other.example/a','https://api.github.com@other.example/a'):
        with pytest.raises(ValueError):safe(url)
    for path in ('../outside.csv','/absolute.csv','folder\\outside.csv'):
        with pytest.raises(ValueError):member_path(tmp_path,tmp_path/'source',path)


def test_invalid_corpus_selections_fail_before_job_creation(tmp_path):
    from baseball_lab.web.server import Workbench
    wb=Workbench(tmp_path)
    options={'study':'pitch_game','source':'retrosheet','pitch_corpus':True}
    for extra in ({'corpus_leagues':[]},{'corpus_seasons':[1900]},{'corpus_seasons':[True]},
                  {'corpus_leagues':['OTHER']},{'study':'half_inning'}):
        with pytest.raises(ValueError):wb.start('run',{**options,**extra})
    assert not list(wb.outputs.glob('*/task.json'))
