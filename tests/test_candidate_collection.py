"""MOCK_TEST_ONLY: acquisition boundaries, never a network or training source."""
import csv
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

spec=importlib.util.spec_from_file_location('candidate_collector',Path(__file__).parents[1]/'scripts/collect_retrosheet_candidate.py')
collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)


def test_candidate_fixed_source_and_no_existing_directory_overwrite(tmp_path):
    with pytest.raises(ValueError,match='공식 후보'):
        collector.download_exact('https://untrusted.example/data.zip',tmp_path/'x.zip',100)
    one=collector.new_candidate_directory(tmp_path);two=collector.new_candidate_directory(tmp_path)
    assert one!=two and one.is_dir() and two.is_dir()
    assert not list(tmp_path.glob('data/local/catalog/*'))


def test_changed_candidate_pin_fails_before_extraction_or_registration(tmp_path):
    def transport(url,destination,limit):
        if url==collector.TERMS_URL:
            destination.write_text('MOCK_TEST_ONLY free to make any desired use copyrighted by Retrosheet '+collector.SOURCE_URL)
        else:destination.write_bytes(b'MOCK_TEST_ONLY changed archive')
    with patch.object(collector,'download_exact',side_effect=transport),patch.object(collector,'extract_csv') as extract:
        with pytest.raises(ValueError,match='검토한 버전'):collector.collect(tmp_path)
    extract.assert_not_called()
    records=list(tmp_path.glob('data/local/retrosheet/candidate-*/candidate-manifest.json'))
    assert len(records)==1
    data=json.loads(records[0].read_text())
    assert data['status']=='CANDIDATE_ACQUISITION_FAILED' and not data['training_registered']
    assert not list(tmp_path.glob('data/local/retrosheet/official-*'))
