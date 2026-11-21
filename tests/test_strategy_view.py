"""MOCK_TEST_ONLY report counters; no fabricated observations enter resources."""
from copy import deepcopy
import json
import pytest
from baseball_lab.experiments.match.pitch_game.strategy_view import heatmap,management,build
from baseball_lab.experiments.match.pitch_game.strategy import new_stats,complete_game


def test_heatmap_denominator_excludes_missing_and_unspecified_not_real_pitches():
    t={'defense':{'pitch':5,'pitch:fastball:inside_low:fast':3,'pitch:slider:any:slow':2,'change_1':1}}
    h=heatmap(t)
    assert (h['total'],h['known'],h['missing'],h['unspecified'])==(10,3,2,5)
    assert h['shares']['inside_low']==1 and sum(h['shares'].values())==1
    assert h['reconciled']
    empty=heatmap({'defense':{'pitch:fastball:any:fast':5}})
    assert empty['known']==0 and set(empty['shares'].values())=={None}


def test_old_marginals_cannot_be_cross_filtered_or_assigned_a_league():
    t={'pitch_area':{'inside_low':3,'unknown':7}}
    assert heatmap(t,'generated')['total']==10
    assert not heatmap(t,'generated',family='fastball')['available']
    assert not heatmap(t,'generated',league='MLB')['available']


def test_joint_heatmap_keeps_source_league_and_family_together():
    t={'pitch_bins':{'generated':{'MLB:2024:MOCK_TEST_ONLY':{'fastball':{'inside_low':3,'unknown':2}},
                                'KBO:2024:MOCK_TEST_ONLY':{'fastball':{'unknown':8}}}}}
    h=heatmap(t,'generated','MLB','fastball')
    assert h['known']==3 and h['missing']==2 and h['total']==5
    k=heatmap(t,'generated','KBO','fastball')
    assert k['known']==0 and k['total']==8


def test_management_uses_games_and_does_not_claim_audit_of_old_totals():
    m=management({'defense':{'change_1':59,'change_2':57}},60)
    assert m['per_game']==pytest.approx(116/60) and not m['audited'] and m['histogram'] is None
    assert not management({'defense':{'change_1':121}},60)['consistent']
    t={'defense':{'change_1':1},'management':{'games':2,'changes':1,'histogram':{'0':1,'1':1},'invalid_changes':0}}
    assert management(t,2)['audited'] and management(t,2)['consistent']
    t['management']['histogram']={'2':2}
    assert not management(t,2)['consistent']


def test_substitution_audit_rejects_reentry_unearned_entry_and_mismatched_counts():
    good={'from_slot':0,'to_slot':1,'batters_faced':3,'inning_break':False,'has_appeared':True}
    stats=new_stats();complete_game(stats,[{'change_1':1},{}],[[good],[]])
    assert stats[0]['management']=={'games':1,'changes':1,'histogram':{'1':1},'invalid_changes':0}
    inning_stats=new_stats();complete_game(inning_stats,[{'change_1':1},{}],[[{**good,'batters_faced':0,'inning_break':True}],[]])
    assert inning_stats[0]['management']['games']==1
    for trace,counts in (([{**good,'has_appeared':False}],{'change_1':1}),([{**good,'batters_faced':2}],{'change_1':1}),
                         ([good,{**good,'from_slot':1}],{'change_1':2}),([] ,{'change_1':1})):
        with pytest.raises(ValueError):complete_game(new_stats(),[counts,{}],[trace,[]])


def mock_result():
    stats=new_stats()
    return {'schema':'Match-pitch-decision-game-v4','status':'COMPLETED','strategy_analysis':{'teams':stats,'preferences':[]},
        'seeds':[{'seed':1,'history':[{'games':0,'strategy_probes':[]}],'training_environments':{},'replay':{'events':[]}}],
        'world':{'cohorts':[{'league':'MLB','season':2024}], 'sources':['MOCK_TEST_ONLY'*10000],
            'holdout_prediction':{'test':{'pitches':1,'brier':.5,'baseline_brier':.5}},'asset_sha256':'MOCK_TEST_ONLY',
            'contact_coverage':{}}}


def test_report_projection_preserves_saved_json_and_omits_repetitive_internals():
    result=mock_result();before=deepcopy(result);view=build(result)
    assert result==before and 'sources' not in view['evidence']
    assert len(json.dumps(view))<len(json.dumps(result))/5
    from baseball_lab.experiments.match.pitch_game.research import render
    html=render(result)
    assert '코스 미지정' in html and '투수 교체 기록' in html and 'MOCK_TEST_ONLY'*100 not in html
    assert result==before
