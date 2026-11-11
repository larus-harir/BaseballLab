"""MOCK_TEST_ONLY: new sampling and explicit replay, without changing physics."""
import json
import re
from pathlib import Path
from unittest.mock import patch
import pytest
from test_matchup import mock_catalog
from baseball_lab.matchup.service import analyze
from baseball_lab.web.server import Workbench


def options():
    return {'batter':'KBO:batter:b1:1982','pitcher':'KBO:pitcher:p1:2024','n':100,'repetitions':2}


def test_default_new_streams_and_exact_explicit_replay(mock_catalog):
    root,_=mock_catalog
    with patch('secrets.randbelow',side_effect=[101,102,103]):
        rows=[analyze(root,'eramatch',options()) for _ in range(3)]
    assert [r['simulation']['seed'] for r in rows]==[101,102,103]
    assert rows[0]['simulation']['events']!=rows[1]['simulation']['events']
    assert all(r['model']['probabilities']==rows[0]['model']['probabilities'] for r in rows)
    a=analyze(root,'eramatch',{**options(),'seed':101})
    b=analyze(root,'eramatch',{**options(),'seed':101})
    assert a['simulation']==b['simulation']==rows[0]['simulation']
    assert a['reading']['events']==b['reading']['events']
    assert a['run_id']==b['run_id']
    with pytest.raises(ValueError,match='당시'):
        analyze(root,'eramatch',{**options(),'seed':101,'expected_run_id':'MOCK_TEST_ONLY outdated dataset'})


def test_execution_identity_is_distinct_from_reproduction_fingerprint(mock_catalog):
    root,_=mock_catalog;wb=Workbench(root)
    a=wb.matchup_analyze('eramatch',{**options(),'seed':99})
    b=wb.matchup_analyze('eramatch',{**options(),'seed':99})
    assert a['analysis']['run_id']==b['analysis']['run_id']
    assert a['analysis']['execution']['execution_id']!=b['analysis']['execution']['execution_id']
    assert a['report']!=b['report']
    for result in (a,b):
        p=wb.outputs/result['analysis']['execution']['execution_id']/'result/analysis.json'
        assert json.loads(p.read_text())['simulation']==a['analysis']['simulation']


@pytest.mark.parametrize('n',[25,100,250])
def test_denominators_and_full_partition(mock_catalog,n):
    root,_=mock_catalog;r=analyze(root,'eramatch',{**options(),'n':n,'seed':17})
    s=r['simulation'];assert n==sum(s['counts'].values())==len(s['events'])
    assert sum(row['count'] for row in r['reading']['rows'])==n
    assert sum(row['probability'] for row in r['reading']['rows'])==pytest.approx(1)
    assert sum(row['expected'] for row in r['reading']['rows'])==pytest.approx(n)


def test_result_templates_have_no_fixed_sample_claims():
    root=Path(__file__).parents[1]/'src/baseball_lab'
    templates=[root/'web/matchup.html',*root.glob('experiments/match/reporting/*.html')]
    for path in templates:
        text=path.read_text()
        assert not re.search(r'\d+번의 가상 대결|<b>\d+타석</b>|value="41"|\d+타석은',text),path


def test_equal_sample_counts_are_valid_for_distinct_streams():
    from baseball_lab.matchup.models import simulate,EVENTS
    q={k:float(k=='other') for k in EVENTS}
    a=simulate({'model':'normalized','probabilities':q},25,101,1)
    b=simulate({'model':'normalized','probabilities':q},25,102,1)
    assert a['seed']!=b['seed'] and a['counts']==b['counts']
