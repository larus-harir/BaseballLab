"""Result interpretation must not invent a winner or confuse opponents."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from baseball_lab.experiments.match.reporting.summary import build_summary, pool, verdict
from baseball_lab.experiments.match.reporting.report import render
from baseball_lab.simulation.scoring import observe
from test_r1 import mock_dataset


def evidence():
    # Archived aggregate evidence; no training or factual claims are fabricated.
    data=json.loads((Path(__file__).parents[1]/'docs/results/e01-r1-2024.json').read_text())
    data['dataset']={**data['source'],'credit':data['credit']}
    return data


def test_actual_evidence_separates_duel_from_growth():
    data=evidence();summary=build_summary(data)
    assert summary['duel']['successes']==704 and summary['duel']['n']==1500
    assert summary['duel']['rate']==pytest.approx(704/1500)
    assert summary['verdict']=='observed'
    assert [g['improved'] for g in summary['growth']]==[False,True]
    assert summary['growth'][1]['before']['successes']==433
    assert summary['growth'][1]['after']['successes']==782
    assert summary['timeline'][0]['rate']==pytest.approx(1040/1500)
    assert summary['timeline'][-1]['rate']==summary['duel']['rate']
    assert summary['choices'][0]['text']=='반복마다 방향이 달라요'


@pytest.mark.parametrize('rates,expected', [([501,501,501],'observed'),([1000,1000,1000],'observed'),([0,0,0],'observed'),([950,950,490],'observed')])
def test_small_or_conflicting_results_do_not_force_a_winner(rates,expected):
    result=pool({'n':1000,'scored':n,'environment_id':'same'} for n in rates)
    assert verdict(result)[0]==expected
    assert verdict(pool([{'n':1000,'scored':900}]))[0]=='observed'
    assert '우세' not in verdict(result)[1]
    assert str(sum(rates)) in verdict(result)[1].replace(',','')


def test_partial_training_missing_evaluation_and_incompatible_environments():
    data=evidence();data['status']='RUNNING'
    assert build_summary(data)['verdict']=='pending'
    data['seeds'][0].pop('test_evaluation')
    assert build_summary(data)['finished_repeats']==2
    data['seeds']=[]
    summary=build_summary(data)
    assert summary['duel'] is None and summary['timeline']==[]
    with pytest.raises(ValueError,match='서로 다른'):
        pool([{'n':100,'scored':60,'environment_id':'a'},{'n':100,'scored':80,'environment_id':'b'}])


def test_render_does_not_mutate_old_evidence_and_preserves_escaping():
    data=evidence();original=deepcopy(data);data['dataset']['provider']='</script><script>unsafe()</script>'
    body=render(data)
    assert '\\u003c/script>' in body and 'id="overview"' in body
    assert 'id="evidence" role="tabpanel" aria-labelledby="tab-evidence" hidden' in body
    assert 'reading' not in data
    data['dataset']['provider']=original['dataset']['provider']
    assert data==original


def test_parent_observer_does_not_train_or_relabel_observed_data(tmp_path):
    data=mock_dataset()
    for i,r in enumerate(data['records']):r['source_row_ids']=[f'MOCK:{i}']
    with pytest.raises(ValueError,match='실제 원천'):observe(data,'2024-05-01','2024-05-05',tmp_path/'blocked')
    with patch('baseball_lab.experiments.match.team_win.training.train',side_effect=AssertionError('must not train')):
        generated=observe(data,'2024-05-01','2024-05-05',tmp_path/'model',test_only=True)
        actual=observe(data,'2024-05-01','2024-05-05',tmp_path/'observed',source='observed',test_only=True)
    assert not generated['training_executed'] and not actual['training_executed']
    assert generated['source_status']==actual['source_status']=='MOCK_TEST_ONLY'
    assert 'source_row_ids' in actual['events'][0] and 'batter_action' not in actual['events'][0]
    assert 'batter_action' in generated['events'][0]
    assert (tmp_path/'observed/report.html').exists()


def test_registered_seasons_and_external_evaluation_guard(tmp_path):
    from baseball_lab.data.retrosheet_releases import RELEASES
    from baseball_lab.r1.provider import acquire
    from baseball_lab.experiments.match.team_win.external import external
    assert set(RELEASES)=={2023,2024}
    with patch('baseball_lab.r1.provider.download') as download:
        with pytest.raises(ValueError):acquire(tmp_path/'unregistered',year=2022)
        download.assert_not_called()
    data=evidence();path=tmp_path/'research.json';path.write_text(json.dumps(data))
    original=path.read_bytes()
    with patch('baseball_lab.experiments.match.team_win.external.acquire') as download:
        with pytest.raises(ValueError,match='다른 시즌'):external(path,2024)
        download.assert_not_called()
    assert path.read_bytes()==original
