"""MOCK_TEST_ONLY: contextual decisions must never become invented causes."""
from copy import deepcopy
import pytest
from baseball_lab.experiments.match.pitch_game.decision_insights import build


def sample(after=(.8,.7)):
    context={'environment':'MLB:2025:MOCK_TEST_ONLY','name':'count_0_2','balls':0,'strikes':2,
        'outs':1,'bases':2,'hand':'R','inning':6,'bottom':1,'difference':-1,
        'cue':'pitch:slider:left_low:slow'}
    def probe(p):return {'id':'MOCK_TEST_ONLY','context':deepcopy(context),'teams':[
        {'offense':{'take':1-p,'swing:pull':p*.75,'swing:opposite':p*.25},
         'defense':{'pitch:cutter:right_high:fast':p,'pitch:fastball:left_low:fast':1-p}}]*2}
    return {'seeds':[{'history':[{'games':0,'strategy_probes':[probe(.5)]},
        {'games':20,'strategy_probes':[probe(p)]}]} for p in after]}


def test_exact_situation_and_opposing_choices_are_not_frequency_or_thoughts():
    d=sample();original=deepcopy(d);stories={s['view']:s for s in build(d)}
    assert d==original
    s=stories['offense']
    assert s['matched_runs']==2 and abs(s['delta'])==pytest.approx(.25)
    assert '0볼 2스트라이크' in s['summary'] and '주자 2루' in s['summary']
    assert '낮은 슬라이더 상대' in s['summary'] and '지켜보기' in s['summary']
    assert '모두에서' in s['reason']
    assert all(s['decisions']==0 and s['signal'] is None for s in stories.values())
    assert '슬라이더' not in stories['defense']['summary']
    assert '때문에' not in str(stories) and '여전히' not in str(stories)


def test_opposite_run_changes_stay_mixed_and_small_changes_are_honest():
    rows=build(sample((.8,.3)));s=next(s for s in rows if s['view']=='offense')
    assert '실행마다 변화 방향' in s['reason']
    assert all('크게 바뀌지' in s['summary'] for s in build(sample((.5,.5))))


def test_mismatched_contexts_or_ids_are_not_paired_or_pooled():
    d=sample();d['seeds'][0]['history'][0]['strategy_probes'][0]['context']['balls']=1
    assert all(s['matched_runs']==1 for s in build(d))
    d=sample();d['seeds'][0]['history'][-1]['strategy_probes'][0]['id']='MOCK_TEST_ONLY_OTHER'
    assert all(s['matched_runs']==1 for s in build(d))
    d=sample()
    for h in d['seeds'][1]['history']:h['strategy_probes'][0]['context']['balls']=1
    assert all(s['matched_runs']==1 for s in build(d))


def test_no_training_no_probes_and_missing_direction_cannot_create_insights():
    assert build({'seeds':[]})==[]
    d=sample()
    for run in d['seeds']:
        for h in run['history']:h['strategy_probes'][0]['teams'][0]['offense']={'take':1.}
    assert 'direction' not in {s['view'] for s in build(d)}
    for run in d['seeds']:run['history'][-1]['games']=0
    assert build(d)==[]


def test_generic_pitch_is_not_presented_as_a_learned_pitch_style():
    d=sample()
    for run in d['seeds']:
        for h in run['history']:h['strategy_probes'][0]['teams'][0]['defense']={'pitch':.5,'intentional_walk':.5}
    assert 'defense' not in {s['view'] for s in build(d)}
