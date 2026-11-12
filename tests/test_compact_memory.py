"""MOCK_TEST_ONLY fault transports and real whitelisted package metadata."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from baseball_lab.data import compact,memory_source
from baseball_lab.data.lineage import checksum,write_json
from baseball_lab.matchup.shared import catalog


def test_bundled_counts_have_only_matchup_fields_and_real_source_lineage():
    rows=compact.players()
    assert len(rows)==compact.index()['players_rows']
    assert {r['league'] for r in rows}=={'MLB','KBO','NPB'}
    assert {r['season'] for r in rows if r['league']=='MLB'}==set(range(2000,2026))
    for r in rows:
        assert set(r['source_fields'])<= {'Name','teams','team_label'}
        assert r['provenance_status'] in ('REAL_OBSERVED','LEGACY_UNVERIFIED')
        assert len(r['source_sha256'])==64 and 'MOCK_TEST_ONLY' not in json.dumps(r)
    assert compact.index()['npb']['attribution'].startswith('This uses data sourced')


def test_windows_cp949_default_cannot_change_utf8_catalog_read(tmp_path):
    from test_shared_execution import prepared
    rows,file=prepared(tmp_path)
    rows[0]['source_fields']['Name']='한글・日本語 MOCK_TEST_ONLY'
    file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    meta=json.loads((file.parent/'manifest.json').read_text(encoding='utf-8'))
    meta['rows_sha256']=checksum(file);write_json(file.parent/'manifest.json',meta)
    original=Path.open
    def cp949_open(path,*args,**kwargs):
        mode=args[0] if args else kwargs.get('mode','r')
        if 'b' not in mode and not kwargs.get('encoding'):kwargs['encoding']='cp949'
        return original(path,*args,**kwargs)
    with patch.object(Path,'open',cp949_open):
        data=catalog(tmp_path)
    assert any(p['name']=='한글・日本語 MOCK_TEST_ONLY' for p in data['profiles'].values())


def test_memory_source_rejects_changed_version_without_writing(tmp_path):
    with patch.object(memory_source,'fetch',return_value=b'MOCK_TEST_ONLY wrong ZIP'):
        with pytest.raises(ValueError,match='SHA-256'):memory_source.season(tmp_path,2025)
    assert not list(tmp_path.rglob('*'))


def test_memory_fetch_only_accepts_reviewed_official_urls():
    with pytest.raises(ValueError,match='공식 시즌'):memory_source.fetch('https://example.invalid/MOCK_TEST_ONLY.zip')


def test_np_b_date_cutoff_has_no_future_observations():
    with pytest.raises(ValueError,match='검사 시작 전'):compact.npb_before('2025-01-01')
    data=compact.npb_before('2025-07-01')
    assert data['dates'][1]<'2025-07-01' and sum(data['counts'].values())>0


def test_windows_crlf_index_keeps_checksum_and_rejects_content_changes(tmp_path):
    import hashlib
    resource=Path(__file__).resolve().parents[1]/'src/baseball_lab/data/resources/index.json'
    original=resource.read_bytes()
    windows=original.replace(b'\n',b'\r\n')
    assert hashlib.sha256(original).hexdigest()==compact.INDEX_SHA256
    assert hashlib.sha256(windows).hexdigest()!=compact.INDEX_SHA256
    folder=tmp_path/'resources';folder.mkdir()
    target=folder/'index.json';target.write_bytes(windows)
    compact.index.cache_clear()
    try:
        with patch.object(compact,'files',return_value=tmp_path):
            assert compact.index()['players_rows']>0
            compact.index.cache_clear()
            target.write_bytes(windows.replace(b'compact-source-index-v1',b'MOCK_TEST_ONLY altered'))
            with pytest.raises(ValueError,match='출처 목록'):compact.index()
    finally:compact.index.cache_clear()
