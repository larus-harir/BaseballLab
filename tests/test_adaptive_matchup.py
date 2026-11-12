"""MOCK_TEST_ONLY coverage combinations; public name bundle checks use real IDs."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pytest
from baseball_lab.data.compact import mlb_names,players
from baseball_lab.matchup.event_schema import model,partition
from baseball_lab.matchup.collected import overview


def fixture(missing=()):
    base={'PA':100,'TBF':100,'H':25,'SO':20,'BB':10,'HBP':2,'2B':4,'3B':1,'HR':5}
    b={'league':'MLB','season':2024,'counts':base.copy()}
    p={'league':'NPB','season':2025,'counts':base.copy()}
    for f in missing:p['counts'][f]=None
    population={'stat_counts':base.copy(),'source_namespace':'MOCK_TEST_ONLY','sample_n':100,'basis':'MOCK_TEST_ONLY'}
    data={'baselines':{k:deepcopy(population) for k in ('MLB:2024','NPB:2025')}}
    return data,b,p


@pytest.mark.parametrize('missing,events',[
    (('2B','3B','HBP'),{'strikeout','walk','hit_other','home_run','other'}),
    (('2B','3B'),{'strikeout','walk','hbp','hit_other','home_run','other'}),
    (('HBP',),{'strikeout','walk','single','double','triple','home_run','other'}),
    ((),{'strikeout','walk','hbp','single','double','triple','home_run','other'}),
    (('HR',),{'strikeout','walk','hbp','hit_other','double','triple','other'}),
])
def test_only_unavailable_splits_are_grouped(missing,events):
    data,b,p=fixture(missing);original=deepcopy((data,b,p))
    m,labels,reference=model(data,b,p,'MLB:2024',100)
    assert set(m['probabilities'])==events==set(labels)
    assert sum(m['probabilities'].values())==pytest.approx(1)
    assert set(m['field_policy']['unmodeled_fields'])==set(missing)
    assert (data,b,p)==original
    for role,player in (('batter',b),('pitcher',p)):
        counts=partition(player['counts'],role,m['field_policy']['retained_optional_fields'])
        assert sum(counts.values())==100
        if 'HR' not in missing:assert counts['home_run']==5


def test_known_zero_home_runs_are_distinct_from_missing_values():
    data,b,p=fixture(('2B','3B'))
    b['counts']['HR']=p['counts']['HR']=0
    for v in data['baselines'].values():v['stat_counts']['HR']=0
    m,_,_=model(data,b,p,'MLB:2024',100)
    assert m['probabilities']['home_run']==0 and 'HR' not in m['field_policy']['unmodeled_fields']


def test_missing_baseline_field_does_not_remove_other_available_events():
    data,b,p=fixture()
    data['baselines']['NPB:2025']['stat_counts']['3B']=None
    m,_,_=model(data,b,p,'MLB:2024',100)
    assert {'double','home_run','hbp'}<=m['probabilities'].keys()
    assert 'triple' not in m['probabilities']
    assert m['field_policy']['unmodeled_fields']['3B']['scopes']==['NPB:2025']


def test_required_exposure_is_never_inferred_and_impossible_partial_splits_rejected():
    with pytest.raises(ValueError):partition({'H':25,'SO':20,'BB':10},'pitcher',[])
    from baseball_lab.data.standard import normalize_season_row
    with pytest.raises(ValueError,match='장타 합계'):
        normalize_season_row(league='MLB',season=2025,role='pitcher',source_player_id='MOCK_TEST_ONLY',source_namespace='MOCK_TEST_ONLY',source_sha256='MOCK_TEST_ONLY',counts={'TBF':100,'H':10,'HR':11})


def test_all_bundled_mlb_players_have_official_names_and_name_search_is_offline(tmp_path):
    names=mlb_names();ids={r['source_player_id'] for r in players() if r['league']=='MLB'}
    assert ids<=names.keys() and len(ids)==7157
    assert names['ohtas001']=='Shohei Ohtani' and names['judga001']=='Aaron Judge'
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY offline')):
        result=overview(tmp_path,'baseball',league='MLB',role='batter',season=2025,query='Ohtani')
    assert result['matched']==1 and result['profiles'][0]['name']=='Shohei Ohtani'
    assert result['profiles'][0]['player_id']=='ohtas001'


def test_unregistered_source_columns_are_retained_without_entering_probability_counts():
    from baseball_lab.data.warehouse import adapt_snapshot
    row={'role':'batter','source_player_id':'MOCK_TEST_ONLY','source_sha256':'MOCK_TEST_ONLY',
         'counts':{'PA':100,'H':25,'SO':20,'BB':10,'HR':5,'FUTURE_PROVIDER_METRIC':99},'source_fields':{'Name':'MOCK_TEST_ONLY'}}
    value=adapt_snapshot(row,{'league':'MLB','season':2025,'granularity':'player_season','source_namespace':'MOCK_TEST_ONLY','source_status':'MOCK_TEST_ONLY'})
    assert value['source_fields']['FUTURE_PROVIDER_METRIC']==99
    assert 'FUTURE_PROVIDER_METRIC' not in value['counts'] and value['counts']['HR']==5
    assert value['counts']['2B'] is None and value['missing_reasons']['2B']=='not_collected'
