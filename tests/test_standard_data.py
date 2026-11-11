"""MOCK_TEST_ONLY league contracts, not empirical research evidence."""
import pytest
from baseball_lab.data.standard import normalize_season_row,select_window,innings_outs


def row(**changes):
    options={'league':'KBO','season':2024,'role':'batter','source_player_id':'MOCK_TEST_ONLY',
             'source_namespace':'MOCK_TEST_ONLY','source_sha256':'MOCK_TEST_ONLY',
             'counts':{'PA':100,'AB':80,'H':20,'SO':30,'BB':15,'2B':4,'3B':1,'HR':3}}
    options.update(changes);return normalize_season_row(**options)


def test_missing_is_not_zero_or_training_eligibility():
    r=row();assert r['counts']['HBP'] is None and r['events'] is None
    assert r['missing_reasons']['HBP']=='not_collected'
    assert not r['eligibility']['policy_learning']
    c={**r['counts'],'HBP':0};r=row(counts=c)
    assert sum(r['events'].values())==100 and r['eligibility']['categorical_partition']
    assert not r['eligibility']['cross_league_calibrated']


def test_broken_denominators_unknown_fields_and_ambiguous_zero_rejected():
    for changes in ({'H':101},{'SO':-1},{'BB':True},{'PA':float('nan')},{'PA':100,'H':80,'SO':40},{'2B':30}):
        with pytest.raises(ValueError):row(counts={**row()['counts'],**changes})
    with pytest.raises(ValueError):row(counts={'HP':1})
    with pytest.raises(ValueError):row(counts={'HBP':0},missing_reasons={'HBP':'ambiguous_definition'})
    assert row(missing_reasons={'HBP':'ambiguous_definition'})['counts']['HBP'] is None


def test_recent_window_preserves_each_league_and_does_not_merge_names():
    rows=[row(league=league,season=year) for league,years in [('MLB',[2021,2022,2023,2024]),('NPB',[2020,2021,2022])] for year in years]
    recent=select_window(rows,last_seasons=2)
    assert {(r['league'],r['season']) for r in recent}=={('MLB',2023),('MLB',2024),('NPB',2021),('NPB',2022)}
    assert len({r['entity_id'] for r in rows})==len(rows)
    with pytest.raises(ValueError):select_window(rows+[rows[0]])
    with pytest.raises(ValueError):select_window([row(),row(row_kind='team_split',team='MOCK_TEAM')])


def test_baseball_innings_are_outs_not_decimal_innings():
    assert innings_outs('16.1')==49 and innings_outs('0.2')==2
    for invalid in ('16.3','16.5','16.11','-1.0'):
        with pytest.raises(ValueError):innings_outs(invalid)
