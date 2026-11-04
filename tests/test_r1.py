"""Explicit mock inputs test implementation; real evidence lives in the run report."""
import csv
import json
from random import Random
from unittest.mock import patch

import numpy as np
import pytest
from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.data.lineage import content_hash
from baseball_lab.r1.data import normalize, walk, load
from baseball_lab.r1.environment import Observation, Environment, STATES, fit, key, policy, restore
from baseball_lab.r1.provider import acquire
from baseball_lab.r1.training import Config, Fixed, train


@pytest.mark.parametrize('bases,after,runs', [(0,1,0),(1,3,0),(2,3,0),(3,7,0),(4,5,0),(5,7,0),(6,7,0),(7,7,1)])
def test_intentional_walk_forces_only_necessary_runners(bases, after, runs):
    assert walk(bases) == (after,runs)


def test_masked_policy_gradient_and_no_unsupported_choices():
    p=policy('batter',31); obs=Observation(0,0)
    p.collect=True
    assert p.probabilities(obs,('ordinary_turn',)).tolist()==[1.,0.]
    assert {p.act(obs,('ordinary_turn',),Random(s)) for s in range(10)}=={'ordinary_turn'}
    p=NeuralPolicy('batter',5,hidden=3,actions=('a','b','c'))
    x=np.ones((2,len(p.feature_names)));actions=np.array([0,2]);advantages=np.array([1.,-.5])
    masks=np.array([[1,0,1],[0,1,1]],dtype=bool)
    _,grads=p.gradients(x,actions,advantages,2,masks)
    for param,grad in zip(p.params,grads):
        for index in (tuple(0 for _ in param.shape),tuple(n-1 for n in param.shape)):
            orig=param[index];eps=1e-5
            param[index]=orig+eps;plus=p.gradients(x,actions,advantages,2,masks)[0]
            param[index]=orig-eps;minus=p.gradients(x,actions,advantages,2,masks)[0]
            param[index]=orig
            assert grad[index]==pytest.approx((plus-minus)/(2*eps),abs=1e-7)
    for bad in ((),('unknown',),('a','a')):
        with pytest.raises(ValueError):p._mask(bad)


def mock_dataset():
    rows=[]
    for day in ('01','02','03','04','05'):
        for outs,bases in STATES:
            for action,n in [('ordinary_turn',40),('bunt_attempt',35)]:
                for i in range(n):
                    rows.append({'record_id':f'MOCK:{day}:{outs}:{bases}:{action}:{i}',
                                 'game_id':'MOCK'+day,'date':'2024-05-'+day,
                                 'outs':outs,'bases':bases,'action':action,'intentional_walk':False,
                                 'outs_added':1 if i%3 else 0,'runs':0 if i%3 else 1,
                                 'end_bases':bases,'event_codes':[2 if i%3 else 20]})
    return {'manifest':{'source_status':'MOCK_TEST_ONLY','dataset_id':content_hash(rows),
                        'provider':'Explicit mock fixture','games':5,'raw_event_rows':len(rows),
                        'sequence_mismatches':0,'credit':'MOCK TEST ONLY'},'records':rows}


def test_game_split_action_support_is_not_selected_using_test():
    dataset=mock_dataset();envs,model=fit(dataset,'2024-05-01','2024-05-05')
    assert model['legal_actions_selected_without_test']
    assert model['split']['fit']['dates']==['2024-05-01','2024-05-03']
    assert model['split']['test']['dates']==['2024-05-05','2024-05-05']
    changed=mock_dataset()
    changed['records']=[r for r in changed['records'] if not(r['date']=='2024-05-05' and r['action']=='bunt_attempt')]
    # Do not mask after seeing absent final-period support; fail rather than fabricate.
    with pytest.raises(ValueError,match='test:'):
        fit(changed,'2024-05-01','2024-05-05')
    for env in envs.values():
        for cell in env.cells.values():
            assert all(r['date'] in model['split'][env.name]['dates'] or env.name=='fit' for r in cell)
    empty=mock_dataset();empty['records']=empty['records'][:1]
    with pytest.raises(ValueError):fit(empty,'2024-05-01','2024-05-05')


def test_scoring_reward_and_predecision_state_no_leakage():
    envs,_=fit(mock_dataset(),'2024-05-01','2024-05-05');env=envs['fit']
    class Inspect:
        def __init__(self,action):self.action=action
        def act(self,obs,legal,rng):
            assert set(vars(obs))=={'outs','bases'}
            return self.action
    reward,events=env.play(Inspect('ordinary_turn'),Inspect('intentional_walk'),17,start=(0,7),record=True)
    assert reward==1 and events[0]['runs']==1 and events[0]['transition']['source_status']=='RULE_DERIVED'
    b,p=policy('batter',8),policy('pitcher',9)
    assert env.play(b,p,42,record=True)==env.play(b,p,42,record=True)
    assert np.array_equal(b.probabilities(Observation(0,1)),restore(b.state_dict()).probabilities(Observation(0,1)))


def test_real_path_rejects_mock_and_no_network_fake_fallback(tmp_path):
    with pytest.raises(ValueError,match='실제 원천'):
        train(mock_dataset(),'2024-05-01','2024-05-05',tmp_path/'denied',Config(20,(5,),20,20))
    with patch('baseball_lab.r1.provider.download',side_effect=RuntimeError('PROXY CONNECT 403')):
        with pytest.raises(RuntimeError,match='403'):acquire(tmp_path/'network')
    assert not list((tmp_path/'network').glob('*/dataset.json'))


def test_both_learn_checkpoints_independent_evaluation_and_reproducibility(tmp_path):
    config=Config(32,(41,),16,20,8)
    a=train(mock_dataset(),'2024-05-01','2024-05-05',tmp_path/'a',config,test_only=True)
    b=train(mock_dataset(),'2024-05-01','2024-05-05',tmp_path/'b',config,test_only=True)
    assert a['seeds'][0]['history']==b['seeds'][0]['history']
    assert a['source_status']=='MOCK_TEST_ONLY'
    run=a['seeds'][0]
    assert run['both_parameters_changed']
    assert len(run['cross_play'])==9 and len(run['checkpoints'])==3
    assert {r['opponent'] for r in run['test_evaluation']}=={'fixed','initial','past','third_human_frequency','self'}
    assert not {r['environment_id'] for r in run['test_evaluation']} & {r['environment_id'] for h in run['history'] for r in h['validation_evaluation']}
    assert (tmp_path/'a/report.html').exists()
    with pytest.raises(ValueError,match='덮어쓰지'):train(mock_dataset(),'2024-05-01','2024-05-05',tmp_path/'a',config,test_only=True)


def test_normalizer_keeps_runner_events_and_failed_bunts(tmp_path):
    fields='GAME_ID INN_CT BAT_HOME_ID OUTS_CT PITCH_SEQ_TX AWAY_SCORE_CT HOME_SCORE_CT EVENT_TX EVENT_CD BAT_EVENT_FL EVENT_OUTS_CT BUNT_FL INN_END_FL PA_NEW_FL PA_TRUNC_FL START_BASES_CD END_BASES_CD EVENT_RUNS_CT'.split()
    def row(**updates):
        return dict.fromkeys(fields,'0')|{'GAME_ID':'TST202405010','INN_CT':'1','PITCH_SEQ_TX':'M','BAT_EVENT_FL':'F','BUNT_FL':'F','INN_END_FL':'F','PA_NEW_FL':'T','EVENT_CD':'4',**updates}
    rows=[row(START_BASES_CD='1',END_BASES_CD='2'),row(PA_NEW_FL='F',START_BASES_CD='2',END_BASES_CD='2',EVENT_CD='2',BAT_EVENT_FL='T',EVENT_OUTS_CT='1')]
    p=tmp_path/'mock.csv'
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    d=normalize(p,tmp_path/'out',{},test_only=True)
    assert len(d['records'])==1 and d['records'][0]['action']=='bunt_attempt'
    assert d['records'][0]['bases']==1 and d['records'][0]['end_bases']==2
    assert d['records'][0]['source_status']=='MOCK_TEST_ONLY'
    with pytest.raises(ValueError):load(tmp_path/'out/dataset.json')
    rows[1]['START_BASES_CD']='1'
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError,match='sequence mismatch'):normalize(p,tmp_path/'bad',{},test_only=True)


def test_official_csv_preserves_non_pa_walkoff_and_excludes_postseason(tmp_path):
    from baseball_lab.r1.data import official_rows
    from collections import Counter
    required=['gid','event','inning','vis_home','score_v','score_h','pitches','pa','bunt','iw','outs_pre','outs_post','runs','pn','gametype','pbp',*[f'br{i}_{s}' for i in (1,2,3) for s in ('pre','post')]]
    def play(**updates):
        return dict.fromkeys(required,'')|dict(gid='TST202405010',event='WP.3-H',inning='9',vis_home='1',score_v='0',score_h='0',pa='0',bunt='0',iw='0',outs_pre='1',outs_post='1',runs='1',pn='1',gametype='regular',pbp='full',br3_pre='MOCKRUNNER')|updates
    rows=[play(),play(gid='TST202405020',event='IW',iw='1',pa='1',br1_post='MOCKBATTER',runs='0'),play(gametype='worldseries'),play(gid='TST202405030',event='NP',outs_pre='3',outs_post='3',pa='0',runs='0',br3_pre='')]
    path=tmp_path/'official-schema-mock.csv'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,required);writer.writeheader();writer.writerows(rows)
    stats=Counter();mapped=list(official_rows(path,stats))
    assert len(mapped)==2 and mapped[0]['GAME_END_FL']=='T'
    assert stats=={'all_download_rows':4,'excluded_non_regular_or_non_full':1,'excluded_post_inning_no_play':1}
    dataset=normalize(path,tmp_path/'out',{},official=True,test_only=True)
    assert len(dataset['records'])==2
    assert dataset['records'][0]['truncated'] and dataset['records'][0]['runs']==1
    assert dataset['records'][0]['source_row_ids']==['TST202405010:play1:csvline2']
    assert dataset['manifest']['source_exclusions'][0]['source_row_id']=='TST202405030:play1:csvline5'
    # A 2023 administrative NP before the automatic extra-inning runner is
    # not a transition from empty bases. The next actual row supplies its state.
    admin=[play(gid='TST202305010',inning='10',event='NP',outs_pre='0',outs_post='0',pa='0',runs='0',br3_pre=''),
           play(gid='TST202305010',inning='10',event='K',pn='2',pitches='BFS',outs_pre='0',outs_post='1',pa='1',runs='0',br3_pre='',br2_pre='MOCKRUNNER',br2_post='MOCKRUNNER')]
    admin_path=tmp_path/'administrative.csv'
    with admin_path.open('w',newline='') as f:
        writer=csv.DictWriter(f,required);writer.writeheader();writer.writerows(admin)
    with pytest.raises(ValueError,match='sequence mismatch'):
        normalize(admin_path,tmp_path/'unmapped',{},official=True,test_only=True)
    cleaned=normalize(admin_path,tmp_path/'mapped',{},official=True,test_only=True,skip_empty_no_play=True)
    assert len(cleaned['records'])==1 and cleaned['records'][0]['bases']==2
    assert cleaned['manifest']['download_filter_counts']['excluded_administrative_no_play']==1
    rows[-1]['runs']='1'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,required);writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='Invalid observed transition'):
        normalize(path,tmp_path/'invalid',{},official=True,test_only=True)


def test_bunt_effect_ablation_changes_only_bunt_donors():
    env=fit(mock_dataset(),'2024-05-01','2024-05-05')[0]['test']
    control=env.bunt_effect_ablation()
    assert control.model_id!=env.model_id
    for outs,bases in STATES:
        assert control.cells[key(outs,bases,'bunt_attempt')]==env.cells[key(outs,bases,'ordinary_turn')]
        assert control.cells[key(outs,bases,'ordinary_turn')]==env.cells[key(outs,bases,'ordinary_turn')]
