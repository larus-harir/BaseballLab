"""MOCK_TEST_ONLY catalogs cover source routing without private data/network."""
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import io
import hashlib
import json

import pytest

from baseball_lab.data.catalog import DatasetCatalog
from baseball_lab.matchup.catalog import save_catalog,source_directory
from baseball_lab.matchup import mlb
from baseball_lab.matchup.models import EVENTS
from test_matchup import mock_catalog


def test_descriptor_is_read_only_and_reuses_connected_assignment(mock_catalog):
    root,data=mock_catalog;catalog=DatasetCatalog(root)
    path=root/'data/local/catalog/kbo-assignment/catalog.json';before=path.read_bytes()
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('no network in cache path')):
        descriptor=catalog.describe('eramatch',1982)
        assert descriptor['ready'] and not descriptor['needs_connection']
        assert descriptor['metadata']['status']=='LEGACY_UNVERIFIED'
        assert descriptor['metadata']['entity_ids']['names_are_identifiers'] is False
        assert descriptor['supported_seasons']==[1982,2024]
        assert catalog.ensure('eramatch',1982)['dataset_id']==data['dataset_id']
    assert before==path.read_bytes()


def test_missing_sources_have_explicit_readiness_without_creation(tmp_path):
    c=DatasetCatalog(tmp_path)
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('no network during readiness')):
        b=c.describe('baseball',2023);k=c.describe('eramatch');m=c.describe('match',2024)
    assert not b['ready'] and b['automatic_preparation'] and b['supported_seasons']==[2023,2024]
    assert k['ready'] and not k['needs_connection'] and k['supported_seasons']==list(range(1982,2026))
    assert k['metadata']['included_with_application']
    assert not m['ready'] and m['automatic_preparation']
    assert not list(tmp_path.rglob('*'))
    for invalid in (2025,'2024',True):
        with pytest.raises(ValueError):c.ensure('baseball',invalid)
    with pytest.raises(ValueError):c.get('arbitrary-url',2024)


def test_preparation_routes_exact_season_and_propagates_cancellation(tmp_path):
    c=DatasetCatalog(tmp_path);messages=[]
    def provider(root,year,progress=None):
        assert root==tmp_path and year==2023
        progress('MOCK_TEST_ONLY prepare')
        return {'schema':'MOCK_TEST_ONLY'}
    with patch.object(mlb,'prepare',side_effect=provider) as call:
        assert c.ensure('baseball',2023,progress=messages.append)['schema']=='MOCK_TEST_ONLY'
        assert call.call_count==1
    assert messages[-1]=='MOCK_TEST_ONLY prepare'
    class Cancelled(Exception):pass
    def cancel(message):raise Cancelled(message)
    with patch.object(mlb,'prepare') as call:
        with pytest.raises(Cancelled):c.ensure('baseball',2023,progress=cancel)
        call.assert_not_called()


def test_existing_mlb_catalog_is_not_rebuilt_or_rewritten(tmp_path):
    directory=source_directory(tmp_path,'mlb-2024');directory.mkdir(parents=True)
    data={'schema':'player-season-catalog-v1','source':{'id':'mlb-2024','files':[],'label':'MOCK_TEST_ONLY','acquired_at':'MOCK_TEST_ONLY'},'profiles':{}}
    save_catalog(directory,data);before=(directory/'catalog.json').read_bytes()
    with patch.object(mlb,'acquire',side_effect=AssertionError('must reuse valid catalog')):
        assert mlb.prepare(tmp_path)['dataset_id']==data['dataset_id']
    assert (directory/'catalog.json').read_bytes()==before
    (directory/'catalog.json').write_text('{}')
    with patch.object(mlb,'acquire') as acquire:
        with pytest.raises((ValueError,KeyError)):mlb.prepare(tmp_path)
        acquire.assert_not_called()


def test_registered_roster_checksum_ids_and_symlink(tmp_path):
    payload=io.BytesIO()
    with ZipFile(payload,'w') as z:z.writestr('AAA2023.ROS','mock0001,Last,MOCK_TEST_ONLY,R,R,AAA,P\n')
    (tmp_path/'2023eve.zip').write_bytes(payload.getvalue())
    registry={**mlb.ROSTERS,2023:{'url':mlb.ROSTERS[2023]['url'],'sha256':hashlib.sha256(payload.getvalue()).hexdigest()}}
    with patch.object(mlb,'ROSTERS',registry):assert mlb.rosters(tmp_path,2023)=={'mock0001':'MOCK_TEST_ONLY Last'}
    with pytest.raises(ValueError,match='버전'):mlb.rosters(tmp_path,2023)
    (tmp_path/'2023eve.zip').unlink();(tmp_path/'2023eve.zip').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError,match='링크'):mlb.rosters(tmp_path,2023)


def test_year_specific_split_and_frozen_strength_without_retuning():
    rows=[]
    for stage,date in [('fit','20230401'),('validation','20230720'),('test','20230901')]:
        for i,event in enumerate(EVENTS):rows.append({'id':stage+str(i),'game':stage,'date':date,'batter':'b','pitcher':'p','event':event})
    result=mlb.validate(rows,2023,fixed_strength=300)
    assert result['selected_strength']==300 and len(result['validation_candidates'])==1
    assert result['split']['test']['dates']==['20230901','20230901']
    assert 'MLB 2023' in result['scope']
    with pytest.raises(ValueError):mlb.validate(rows,2023,fixed_strength=float('nan'))


def test_unknown_original_archive_never_looks_connected(tmp_path):
    directory=source_directory(tmp_path,'kbo-assignment');directory.mkdir(parents=True)
    (directory/'assignment-original.zip').write_bytes(b'MOCK_TEST_ONLY not the assignment')
    with pytest.raises(ValueError,match='원본 ZIP'):DatasetCatalog(tmp_path).describe('eramatch')
    with pytest.raises(ValueError,match='원본 ZIP'):DatasetCatalog(tmp_path).ensure('eramatch')
    assert not (directory/'catalog.json').exists()


def test_match_manifest_index_rejects_symlink(tmp_path):
    directory=tmp_path/'data/local/retrosheet/official-2024';directory.mkdir(parents=True)
    (directory/'dataset.json').symlink_to(tmp_path/'outside')
    with pytest.raises(ValueError,match='링크'):DatasetCatalog(tmp_path).get('match',2024)


def test_source_index_keeps_other_entries_when_one_is_corrupt(tmp_path):
    directory=source_directory(tmp_path,'kbo-assignment');directory.mkdir(parents=True)
    (directory/'catalog.json').write_text('MOCK_TEST_ONLY malformed json')
    entries=DatasetCatalog(tmp_path).list_sources()
    assert len(entries)==5
    bad=next(d for d in entries if d['source_id']=='kbo-assignment')
    assert not bad['ready'] and bad['error'] and not bad['automatic_preparation']
    assert next(d for d in entries if d['source_id']=='mlb-2023')['automatic_preparation']


@pytest.mark.parametrize('wrong_pin',['manifest','archive'])
def test_match_native_load_cannot_bypass_official_pin(tmp_path,wrong_pin):
    from baseball_lab.data.retrosheet_releases import RELEASES
    directory=tmp_path/'data/local/retrosheet/official-2024';directory.mkdir(parents=True)
    csv=b'MOCK_TEST_ONLY,parsed-record\n'
    (directory/'2024plays.csv').write_bytes(csv)
    (directory/'2024plays.zip').write_bytes(b'MOCK_TEST_ONLY wellformed metadata with wrong archive')
    manifest={'schema':'retrosheet-turn-segments-v1','source_version':RELEASES[2024]['sha256'] if wrong_pin=='archive' else '0'*64,
              'parsed_csv_sha256':hashlib.sha256(csv).hexdigest()}
    (directory/'dataset.json').write_text(json.dumps({'manifest':manifest,'segments':[]}))
    with patch('baseball_lab.r1.data.load') as native_load:
        with pytest.raises(ValueError,match='버전·해시'):DatasetCatalog(tmp_path).get('match',2024)
        with pytest.raises(ValueError,match='버전·해시'):DatasetCatalog(tmp_path).ensure('match',2024)
        native_load.assert_not_called()
