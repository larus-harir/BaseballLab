"""MOCK_TEST_ONLY: event partition and new reward regression checks."""
from copy import deepcopy
from random import Random
from unittest.mock import patch
import json

import pytest
from baseball_lab.matchup.outcome_details import PRIMARY, classify, attach
from baseball_lab.matchup.reading import interpret
from baseball_lab.experiments.match.team_win import half_inning as inning
from baseball_lab.experiments.match.team_win.training import Config, Fixed
from baseball_lab.r1.environment import Observation
from test_r1 import mock_dataset


def event(primary='othout',**updates):
    return dict.fromkeys(PRIMARY,'0')|{'pa':'1',primary:'1','batter':'MOCK_TEST_ONLY','event':'63/G','ground':'1',**updates}


def test_residual_partition_and_force_out_is_not_batter_out():
    assert classify(event('k')) is None
    assert classify(event())=='ground_out'
    assert classify(event(event='64(1)/FO/G6.B-1'))=='runner_out'
    assert classify(event(br1_post='MOCK_TEST_ONLY'))=='runner_out'
    assert classify(event(gdp='1'))=='grounded_double_play'
    assert classify(event('sh',gdp='1'))=='sacrifice_bunt'
    assert classify(event('sf',fly='1'))=='sacrifice_fly'
    assert classify(event('roe'))=='reached_error'
    assert classify(event('fc'))=='fielders_choice'
    assert classify(event('xi'))=='interference'
    assert classify(event('noout'))=='unresolved'
    assert classify({'pa':'0'}) is None
    with pytest.raises(ValueError): classify(event(walk='1'))
    with pytest.raises(ValueError): classify({'pa':'1'})


def result(project='baseball'):
    from baseball_lab.matchup.models import EVENTS
    seq=['other','strikeout','single','other','walk','double','hbp','other']
    counts={k:seq.count(k) for k in EVENTS}
    return {'project':project,'run_id':'MOCK_TEST_ONLY','batter':{'season':2024,'player_id':'b'},
            'pitcher':{'player_id':'p'},'model':{'model':'normalized','probabilities':{k:counts[k]/len(seq) for k in EVENTS}},
            'simulation':{'n':len(seq),'events':seq,'counts':counts}}


def test_empirical_display_deduplicates_cohort_and_preserves_primary_draws(tmp_path):
    from collections import Counter
    data={'batters':{'b':Counter(ground_out=4,fly_out=2)},'pitchers':{'p':Counter(ground_out=3)},
          'pairs':{('b','p'):Counter(ground_out=1)},'source_sha256':'MOCK_TEST_ONLY','examples':{}}
    r=result();before=deepcopy(r);rng=Random(9);state=rng.getstate()
    with patch('baseball_lab.matchup.outcome_details.index',return_value=data):
        attach(tmp_path,r);again=attach(tmp_path,deepcopy(before))
    assert r['simulation']==before['simulation'] and r['model']==before['model']
    assert rng.getstate()==state
    assert r['event_display']==again['event_display']
    other=r['event_display']['other'];assert other['observed_pool_n']==8
    assert other['observed_counts']['ground_out']==6
    reading=interpret(r)
    assert sum(v['count'] for v in reading['rows'])==8
    assert sum(v['expected'] for v in reading['rows'])==pytest.approx(8)
    assert sum(v['probability'] for v in reading['rows'])==pytest.approx(1)
    assert reading['extra_base_hits']==1


def test_kbo_residual_does_not_invent_outs(tmp_path):
    r=result('eramatch');attach(tmp_path,r)
    assert r['event_display']['events']==r['simulation']['events']
    assert not r['event_display']['other']['detail_available']
    assert '타석별' in interpret(r)['other']['reason']
    r['model']['model']='legacy';attach(tmp_path,r)
    assert '사구를 따로 계산하지 않는' in r['event_display']['other']['definition']


class Sequenced:
    def batter_actions(self,obs):return ('ordinary_turn',)
    def step(self,obs,b,p,rng):
        # MOCK_TEST_ONLY: scoring on first turn must not end this inning.
        if obs.bases==0:return Observation(0,1),2,{'source_status':'MOCK_TEST_ONLY'}
        return Observation(obs.outs+1,1),0,{'source_status':'MOCK_TEST_ONLY'}


def test_inning_continues_after_scoring_until_three_outs():
    reward,events=inning.play(Sequenced(),Fixed('batter'),Fixed('pitcher'),1,record=True)
    assert reward==2 and len(events)==4 and events[-1]['after']['outs']==3
    assert [e['total_runs'] for e in events]==[2,2,2,2]
    class Endless(Sequenced):
        def step(self,*args):return Observation(0,7),1,{}
    with pytest.raises(RuntimeError,match='확정하지 않습니다'):
        inning.play(Endless(),Fixed('batter'),Fixed('pitcher'),1)


def test_completion_dates_are_copy_only_and_game_grouped():
    d=mock_dataset();original=deepcopy(d)
    dates={r['game_id']:'2024050'+r['game_id'][-1] for r in d['records']}
    dates['MOCK01']='20240505'
    a=inning.completion_aligned(d,dates)
    assert d==original
    assert all(r['date']=='2024-05-05' for r in a['records'] if r['game_id']=='MOCK01')
    assert a['manifest']['original_dataset_id']==d['manifest']['dataset_id']
    with pytest.raises(ValueError):inning.completion_aligned(d,{})


def test_late_and_censored_halves_do_not_enter_new_donors():
    d=mock_dataset()
    for r in d['records']:r.update(inning=1,bottom=0)
    late={**d['records'][-1],'record_id':'MOCK_TEST_ONLY:late','inning':9}
    censored={**d['records'][-1],'record_id':'MOCK_TEST_ONLY:walkoff','game_id':'MOCK_CENSORED','outs':1,'outs_added':0}
    d['records'].extend([late,censored])
    dates={r['game_id']:'20240501' for r in d['records']}
    a=inning.completion_aligned(d,dates)
    assert late not in a['records'] and censored not in a['records']
    assert a['manifest']['donor_population']['excluded_segments']=={'ninth_or_extra_inning':1,'unfinished_half_inning':1}


def test_new_learning_updates_both_roles_and_keeps_test_independent(tmp_path):
    d=mock_dataset();config=Config(20,(7,8,9),10,20)
    a=inning.train(d,'2024-05-01','2024-05-05',tmp_path/'a',config,test_only=True)
    b=inning.train(d,'2024-05-01','2024-05-05',tmp_path/'b',config,test_only=True)
    assert a['schema']==inning.SCHEMA and a['status']=='COMPLETED'
    assert a['reward']['intermediate_shaping']==0 and a['start_state']=={'outs':0,'bases':0}
    assert len(a['seeds'])==3
    for s,t in zip(a['seeds'],b['seeds']):
        assert s['both_parameters_changed'] and s['history']==t['history']
        assert len(s['history'])==3
        assert {r['opponent'] for r in s['test_evaluation']}=={'fixed','initial','past','third_human_frequency','self'}
        assert not {r['environment_id'] for r in s['test_evaluation']} & {r['environment_id'] for h in s['history'] for r in h['validation_evaluation']}
        assert all(x['before']=={'outs':0,'bases':0} for x in [z['events'][0] for z in s['replays']])
    saved=json.loads((tmp_path/'a/research.json').read_text())
    assert saved['status']=='COMPLETED'
    from baseball_lab.experiments.match.reporting.inning import summary,render
    reading=summary(a);assert reading['current']['n']==60
    assert all(g['change']['n']==60 for g in reading['growth'])
    assert '세 아웃까지 득점 쌓기' in render(a)
    with pytest.raises(ValueError,match='덮어쓰지'):
        inning.train(d,'2024-05-01','2024-05-05',tmp_path/'a',config,test_only=True)


def test_new_web_study_is_whitelisted_and_uses_fixed_command(tmp_path):
    from baseball_lab.web.server import Workbench
    w=Workbench(tmp_path)
    options={'source':'retrosheet','study':'half_inning','start':'2024-03-20','end':'2024-09-30','episodes':20,'seed':10}
    for invalid in ('shell; echo secret','nine_innings',None,[]):
        with pytest.raises(ValueError):w.start('run',{**options,'study':invalid})
    with pytest.raises(ValueError):w.start('run',{**options,'source':'statcast'})
    assert not list(w.outputs.glob('*/task.json'))
    with patch('baseball_lab.web.server.threading.Thread') as thread:
        w.start('run',options)
    command=thread.call_args.kwargs['args'][1]
    assert isinstance(command,list) and command[command.index('--mode')+1]=='inning'
    assert command[command.index('--evaluation-n')+1]=='500'
    assert w.job['study']=='half_inning'


def test_new_report_reopens_without_rewriting_research_and_escapes_script(tmp_path):
    from baseball_lab.experiments.match.reporting.inning import render
    from baseball_lab.web.server import Workbench,make_handler
    from http.server import ThreadingHTTPServer
    import threading
    from test_web import call
    d=inning.train(mock_dataset(),'2024-05-01','2024-05-05',tmp_path/'run',Config(20,(10,),20,20),test_only=True)
    d['dataset']['credit']='MOCK_TEST_ONLY </script><img src=x onerror=alert(1)>'
    assert '</script><img' not in render(d)
    wb=Workbench(tmp_path);dest=wb.outputs/'MOCK_TEST_ONLY/result';dest.mkdir(parents=True)
    original=json.dumps(d);(dest/'research.json').write_text(original);(dest/'report.html').write_text('MOCK_TEST_ONLY ORIGINAL REPORT')
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(wb));worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        code,body=call(server,'/reports/MOCK_TEST_ONLY/result/report.html')
        assert code==200 and '세 아웃까지 득점 쌓기' in body.decode()
        assert call(server,'/reports/MOCK_TEST_ONLY/result/research.json')[0]==403
    finally:server.shutdown();server.server_close();worker.join()
    assert (dest/'research.json').read_text()==original
    assert (dest/'report.html').read_text()=='MOCK_TEST_ONLY ORIGINAL REPORT'
