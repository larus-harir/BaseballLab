"""MOCK_TEST_ONLY pooled reports and observational outcome attribution."""
from copy import deepcopy
import pytest
from test_strategy_view import mock_result
from baseball_lab.experiments.match.pitch_game.strategy import new_stats,observe,settle
from baseball_lab.experiments.match.pitch_game.strategy_view import build
from baseball_lab.experiments.match.pitch_game.research import Observation


def test_pooled_runs_sum_choices_and_average_matched_policies_without_mutation():
    d=mock_result();d['schema']='Match-pitch-decision-game-v8';d['seeds']=[]
    for n,p in ((10,.8),(20,.4)):
        stats=new_stats();stats[0]['offense']={'take':n,'swing':n*2}
        stats[0]['feedback']['offense']={'take':{'decisions':n,'contact':0,'hits':0,'home_runs':0}}
        def probe(take):return {'id':'MOCK_TEST_ONLY','context':{'name':'count_1_2','balls':1,'strikes':2},'teams':[{'offense':{'take':take,'swing':1-take},'defense':{'pitch:fastball:left_low:fast':.2,'intentional_walk':.8}}]*2}
        d['seeds'].append({'seed':n,'history':[{'games':0,'strategy':new_stats(),'strategy_probes':[probe(.5)]},{'games':n,'strategy':stats,'strategy_probes':[probe(p)]}], 'training_environments':{},'learning_updates':[{'optimizer_steps':1,'choice_signals':{'offense:take':{'decisions':n,'wins':n/2,'advantage_sum':n*.2}}}]})
    original=deepcopy(d);v=build(d)['overview']
    assert d==original and v['games']==30 and v['offense']=={'take':30,'swing':60}
    assert v['preferences']['offense']['after']['take']==pytest.approx(.6)
    c=next(c for c in v['counts'] if (c['balls'],c['strikes'])==(1,2))
    assert c['preferences']['course']['before']=={'area:left_low':1.}
    assert v['feedback']['offense']['take']['mean_advantage']==pytest.approx(.2)
    assert v['feedback']['offense']['take']['reward_observations']==30
    assert v['counts'][0]['preferences']['course']['states']==0


def test_local_change_does_not_replace_the_paired_overall_average():
    from test_glance_report import sample
    data=sample((.9,.9))
    for seed in data['seeds']:
        old,new=seed['history']
        for h,value in ((old,.5),(new,.1)):
            other=deepcopy(h['strategy_probes'][0])
            other['id']='MOCK_TEST_ONLY_SECOND';other['context']['balls']=1
            other['teams'][0]['offense']={'take':1-value,'swing':value}
            h['strategy_probes'].append(other)
    view=build(data)['overview']
    assert view['preferences']['offense']['states']==4
    assert all(abs(row['delta'])<1e-12 for row in view['overall']['offense'])
    assert abs(next(row['delta'] for row in view['explanations'] if row['view']=='offense'))==pytest.approx(.4)
    data['seeds'][0]['history'][-1]['strategy_probes'][1]['context']['strikes']=1
    view=build(data)['overview']
    assert view['preferences']['offense']['states']==3


def test_contact_kind_and_terminal_outcomes_use_observed_denominators_only():
    stats=new_stats();o=Observation(1,0,0,0,0,0,0,0,0,'MLB',2024)
    action='pitch:cutter:left_low:fast'
    observe(stats,0,action,'swing','out',('swing',),(action,),o,{'kind':'ground','side':'left'},'MLB:2024:MOCK_TEST_ONLY')
    settle(stats,0,action,'swing',1,0,'out')
    observe(stats,0,action,'take','hbp',('take',),(action,),o,None,'MLB:2024:MOCK_TEST_ONLY')
    settle(stats,0,action,'take',0,0,'hbp')
    row=stats[1]['feedback']['defense'][action]
    assert row['decisions']==2 and row['kinds']=={'ground':1}
    assert row['terminal_results']=={'out':1,'hbp':1} and row['outs']==1
    assert row['events']=={'out':1,'hbp':1} and row['hits']==0
