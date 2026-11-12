"""MOCK_TEST_ONLY league mixtures use real-shaped counts and donor identities."""
import csv,json
from collections import Counter
from random import Random
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from baseball_lab.data.lineage import checksum,write_json
from baseball_lab.experiments.match.team_win.mixed import weights,Environment,npb_before,train
from baseball_lab.experiments.match.team_win.training import Config
from baseball_lab.r1.environment import Observation
from test_r1 import mock_dataset
from test_web import web,call


def test_mixture_weights_are_explicit_and_cannot_be_nan_or_negative():
    assert weights({'NPB':2,'MLB':1})=={'MLB':1/3,'NPB':2/3}
    for value in ({},{'KBO':0},{'KBO':True},{'X':1},{'MLB':float('nan')},{'MLB':1e308,'KBO':1e308}):
        with pytest.raises(ValueError):weights(value)


def test_league_counts_change_sampling_but_never_invent_runner_transitions():
    keys=('strikeout','walk','hit','other');rows=[];labels={}
    for i,k in enumerate(keys):
        rows.append({'record_id':'MOCK_TEST_ONLY_'+k,'game_id':'MOCK_TEST_ONLY','outs_added':int(k=='strikeout'),'end_bases':i,'runs':int(k=='hit'),'event_codes':['MOCK_TEST_ONLY']})
        labels[rows[-1]['record_id']]=k
    base=SimpleNamespace(cells={'0:0:ordinary_turn':rows},legal={'0:0:legal':['ordinary_turn']},name='MOCK_TEST_ONLY',model_id='MOCK_TEST_ONLY',batter_actions=lambda obs:('ordinary_turn',))
    ref=dict.fromkeys(keys,.25);target={'rates':dict(zip(keys,(.1,.1,.6,.2)))}
    env=Environment(base,labels,ref,{'KBO':target},{'KBO':1});rng=Random(41);observed=Counter()
    for _ in range(5000):
        env.begin(rng);nxt,runs,evidence=env.step(Observation(0,0),'ordinary_turn','challenge',rng)
        observed[evidence['coarse_event']]+=1
        row=next(r for r in rows if r['record_id']==evidence['donor_record_id'])
        assert (nxt.outs,nxt.bases,runs)==(row['outs_added'],row['end_bases'],row['runs'])
        assert evidence['environment_league']=='KBO' and evidence['donor_league']=='MLB'
    assert observed['hit']/5000==pytest.approx(.6,abs=.03)
    assert env.episode_counts=={'KBO':5000}


def test_npb_calibration_excludes_future_games_even_when_their_values_change(tmp_path):
    root=tmp_path;p=root/'data/local/community/npb-armstjc/MOCK_TEST_ONLY';p.mkdir(parents=True)
    pbp=p/'pbp.csv';pbp.write_text('game_id,game_date,game_type_id,game_type_name\nMOCK_TEST_ONLY_before,2025-06-01,1,セ・リーグ公式戦\nMOCK_TEST_ONLY_after,2025-08-01,1,セ・リーグ公式戦\n')
    stats=p/'stats.csv';header='game_id,game_date,player_id,team_id,batting_PA,batting_SO,batting_BB,batting_H\n'
    before='MOCK_TEST_ONLY_before,2025-06-01,MOCK_TEST_ONLY,T,100,20,10,30\n';after='MOCK_TEST_ONLY_after,2025-08-01,MOCK_TEST_ONLY,T,100,99,0,0\n'
    def update(tail):
        stats.write_text(header+before+tail)
        write_json(p/'manifest.json',{'rights_status':'MOCK_TEST_ONLY','license':{'attribution':'MOCK_TEST_ONLY'},'files':[{'kind':kind,'path':str(path.relative_to(root)),'sha256':checksum(path)} for kind,path in [('pbp',pbp),('game_stats',stats)]]})
    update(after);a=npb_before(root,'2025-07-01');update(after.replace('100,99,0,0','100000,1,1,1'));b=npb_before(root,'2025-07-01')
    assert a['counts']==b['counts']=={'strikeout':20,'walk':10,'hit':30,'other':40}
    assert a['dates']==['2025-06-01','2025-06-01']


def test_shared_neural_policy_updates_and_records_each_league_exposure(tmp_path):
    data=mock_dataset();labels={r['record_id']:'hit' if r['runs'] else 'other' for r in data['records']}
    ref=dict.fromkeys(('strikeout','walk','hit','other'),.25)
    targets={l:{'rates':ref,'counts':dict.fromkeys(ref,25),'dates':['2024-05-01','2024-05-03'],'provider':'MOCK_TEST_ONLY'} for l in ('MLB','KBO','NPB')}
    result=train(tmp_path,data,'2024-05-01','2024-05-05',tmp_path/'run',Config(40,(41,),20,20),{'MLB':1,'KBO':1,'NPB':1},test_only=True,prepared_labels=labels,prepared_targets=(ref,targets))
    s=result['seeds'][0]
    assert result['status']=='COMPLETED' and s['both_parameters_changed']
    assert set(s['league_exposure'])=={'MLB','KBO','NPB'} and sum(s['league_exposure'].values())==40
    assert len(s['per_league_evaluation'])==6
    assert result['model']['mixture']['league_identity_observed_by_policy'] is False
    assert all(e['transition']['donor_league'] in ('MLB','RULE') for replay in s['replays'] for e in replay['events'])
    assert s['history'][0]['league_exposure']=={}


def test_bad_mixture_rejected_before_web_task_or_process(web):
    wb,server=web
    opts={'source':'retrosheet','study':'half_inning','start':'2024-03-20','end':'2024-09-30','league_mixture':{'MLB':float('inf')}}
    with patch.object(wb,'_worker',side_effect=AssertionError('MOCK_TEST_ONLY no worker')):
        code,_=call(server,'/api/start','POST',json.dumps({'kind':'run','options':opts}),{'X-Lab-Token':wb.token})
    assert code==400 and not list(wb.outputs.glob('*/task.json'))


def test_kbo_calibration_uses_completed_prior_season_not_current_season():
    from baseball_lab.experiments.match.team_win.mixed import targets
    keys=('strikeout','walk','hit','other');ref=dict.fromkeys(keys,.25)
    rows=[{'record_id':k,'date':'2025-05-01'} for k in keys];labels={k:k for k in keys}
    data={'dataset_id':'MOCK_TEST_ONLY','baselines':{
        'KBO:2024':{'counts':dict.fromkeys(keys,25),'rates':ref,'source_namespace':'MOCK_TEST_ONLY'},
        'KBO:2025':{'counts':dict.fromkeys(keys,9999),'rates':ref,'source_namespace':'MOCK_TEST_ONLY_FUTURE'}}}
    with patch('baseball_lab.experiments.match.team_win.mixed.shared.catalog',return_value=data):
        _,value=targets('.',{'KBO':1},'2025-07-13',rows,labels)
    assert value['KBO']['dates']==['2024-01-01','2024-12-31']
    assert sum(value['KBO']['counts'].values())==100
