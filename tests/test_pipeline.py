from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from baseball_lab.research.pipeline import Plan,run,selected_dataset
from baseball_lab.data.lineage import write_json


def test_period_splits_are_ordered_and_nonoverlapping():
    assert Plan('2024-05-01','2024-05-06').boundaries==('2024-05-04','2024-05-05')
    assert Plan('2024-05-01','2024-05-03').boundaries==('2024-05-02','2024-05-03')
    for end in ('2024-05-02','2024-05-16','2024-04-30'):
        with pytest.raises(ValueError):Plan('2024-05-01',end)


def test_missing_source_never_falls_back_to_mock_or_network(tmp_path):
    with patch('baseball_lab.research.pipeline.acquire') as download:
        with pytest.raises(PermissionError,match='허용 근거'):
            run(Plan('2024-05-01','2024-05-06'),tmp_path/'absent',tmp_path/'run')
        download.assert_not_called()
    assert (tmp_path/'run/failure.json').exists()
    assert not (tmp_path/'run/learning').exists()


def test_exact_period_filter_and_automatic_pipeline(tmp_path):
    # Use the existing explicit MOCK_TEST_ONLY fixture builder; no research claims.
    from test_evidence import fixture_data
    root,source,data=fixture_data.__wrapped__(tmp_path)
    result=run(Plan('2024-05-01','2024-05-03'),root/'data',root/'automatic',episodes=24,
               test_only=True,progress=lambda *a,**k:None)
    assert result['training_executed'] and not result['research_executed']
    assert (root/'automatic/learning/checkpoints/pa_000024.json').exists()
    assert (root/'automatic/report.html').exists()
    filtered=selected_dataset(data,Plan('2024-05-02','2024-05-04'),root/'selection')
    assert all(r['game_date']>='2024-05-02' for r in filtered['records'])
    assert filtered['manifest']['used_rows']==192
