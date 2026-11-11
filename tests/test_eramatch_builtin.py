"""Real supplied season aggregates are application data, not a synthetic fallback."""
import json
from unittest.mock import patch

import pytest

from baseball_lab.data.catalog import DatasetCatalog
from baseball_lab.experiments.eramatch import builtin
from baseball_lab.matchup.service import analyze,overview
from test_web import web,call


def test_empty_installation_runs_report_example_offline_without_files(tmp_path):
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('no network for included KBO')):
        registry=DatasetCatalog(tmp_path);meta=registry.describe('eramatch',2024)
        assert meta['ready'] and not meta['needs_connection']
        assert meta['supported_seasons']==list(range(1982,2026))
        assert meta['metadata']['included_with_application']
        assert meta['metadata']['status']=='LEGACY_UNVERIFIED'
        assert registry.ensure('eramatch')['dataset_id']==meta['metadata']['dataset_id']
        b=overview(tmp_path,'eramatch',role='batter',query='김도영',season=2024)['profiles'][0]
        p=overview(tmp_path,'eramatch',role='pitcher',query='선동열',season=1986)['profiles'][0]
        result=analyze(tmp_path,'eramatch',{'batter':b['id'],'pitcher':p['id'],'seed':41,'n':25,'repetitions':2})
    assert result['model']['model']=='legacy' and len(result['simulation']['events'])==25
    assert result['data_delivery']['kind']=='application_included_season_aggregates'
    assert not result['data_delivery']['original_files_at_runtime']
    assert result['data_delivery']['files'][0]['sha256']==builtin.BUNDLE_SHA256
    assert result['simulation']['counts']=={'strikeout':6,'walk':0,'hbp':0,'single':3,'double':0,'triple':0,'home_run':0,'other':16}
    assert not list(tmp_path.rglob('*'))


def test_package_contains_only_matchup_fields_and_original_version():
    catalog=builtin.load_builtin()
    assert len(catalog['profiles'])==17116
    assert catalog['dataset_id']=='b2338599235c8707566afed1fed7f68ef0852a9758c8fb9ee350cf7e2f3da135'
    for player in catalog['profiles'].values():
        assert not set(player)&{'Birthdate','School','Draft','Handedness','Age','Pos.'}
        assert set(player)<=builtin.PROFILE_FIELDS
        for field in ('counts','legacy_row'):
            if player.get(field):assert set(player[field])<=builtin.COUNT_FIELDS
    metadata=builtin.verification()
    assert metadata['sha256']==builtin.BUNDLE_SHA256
    assert 'compilation' in metadata['scope']


def test_modified_bundle_is_rejected_even_after_cache_warmed(tmp_path):
    builtin.load_builtin()
    resource=tmp_path/'resources';resource.mkdir()
    (resource/builtin.BUNDLE_NAME).write_bytes(b'MOCK_TEST_ONLY modified package data')
    with patch.object(builtin,'files',return_value=tmp_path):
        with pytest.raises(ValueError,match='버전'):builtin.load_builtin()


def test_http_empty_installation_has_players_and_no_upload_control(web):
    wb,server=web
    status,html=call(server,'/eramatch');assert status==200
    assert 'type="file"' not in html.decode() and '원본 연결하고' not in html.decode()
    status,body=call(server,'/api/matchup/catalog?project=eramatch&season=2024&role=batter&query=%EA%B9%80%EB%8F%84%EC%98%81')
    data=json.loads(body)
    assert status==200 and data['ready'] and data['profiles'][0]['name']=='김도영'
    assert not list((wb.root/'data/local').rglob('*'))
