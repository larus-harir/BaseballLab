"""Shared interface properties; fixtures remain MOCK_TEST_ONLY."""
from copy import deepcopy
import pytest
from test_matchup import mock_catalog
from baseball_lab.matchup.catalog import save_catalog
from baseball_lab.matchup.service import analyze
from baseball_lab.simulation.contracts import validate_outcomes,validate_player_season,observation_contract


def test_statistical_programs_emit_same_contract_and_legacy_identity(mock_catalog):
    root,c=mock_catalog;b=c['profiles']['KBO:batter:b1:1982'];p=c['profiles']['KBO:pitcher:p1:2024']
    options={'batter':b['id'],'pitcher':p['id'],'n':25,'repetitions':2}
    automatic=analyze(root,'eramatch',options)
    explicit=analyze(root,'eramatch',{**options,'model':'legacy'})
    assert automatic['simulation']==explicit['simulation']
    assert automatic['run_id']==explicit['run_id']
    contract=automatic['contract']
    assert contract['mode']=='independent_pa' and contract['simulation_count']==25
    assert contract['result_status']=='MODEL_SIMULATED' and contract['source_status']=='LEGACY_UNVERIFIED'
    assert contract['coverage']['batter_n']==400  # Original first eligible team row, not merged800.
    assert not contract['coverage']['hbp_modeled']
    assert contract['dataset_ids']==[c['dataset_id']]
    assert contract['uncertainty']['model_uncertainty_estimated'] is False


def test_auto_selects_available_events_and_records_change(mock_catalog):
    root,c=mock_catalog;b=c['profiles']['KBO:batter:b1:1982'];p=c['profiles']['KBO:pitcher:p1:2024']
    b['legacy_eligible']=False
    save_catalog(root/'data/local/catalog/kbo-assignment',c)
    r=analyze(root,'eramatch',{'batter':b['id'],'pitcher':p['id'],'repetitions':1})
    assert r['model']['model']=='normalized'
    assert r['model_selection']['requested']=='auto' and r['model_selection']['selected']=='normalized'
    assert r['contract']['probability_status']=='EMPIRICALLY_ESTIMATED'
    assert r['model_status']=='UNVALIDATED_COMPARISON'
    with pytest.raises(ValueError,match='원본 방식'):analyze(root,'eramatch',{'batter':b['id'],'pitcher':p['id'],'model':'legacy'})


def test_profile_denominator_and_distribution_contract_rejects_corruption(mock_catalog):
    _,c=mock_catalog;b=deepcopy(c['profiles']['KBO:batter:b1:1982'])
    validate_player_season(b)
    b['counts']['PA']+=1
    with pytest.raises(ValueError,match='분모'):validate_player_season(b)
    with pytest.raises(ValueError):validate_outcomes({'home_run':1.})
    from baseball_lab.matchup.models import distribution
    q=distribution(c['profiles']['KBO:batter:b1:1982']['events']);q['home_run']+=.1
    with pytest.raises(ValueError,match='합'):validate_outcomes(q)


def test_contextual_trace_contract_does_not_invent_event_probabilities():
    result={'source_status':'REAL_OBSERVED','dataset_id':'MOCK_TEST_ONLY','seed':41,'events':[{'runs':0}]}
    c=observation_contract(result)
    assert c['mode']=='contextual_trace' and c['coverage']['probabilities_available'] is False
    assert c['model_version']=='observed-turn-v1' and c['result_status']=='REAL_OBSERVED'
    assert c['simulation_count']==1
