"""Actual defenses, on disposable files only. No research collection is deleted."""
import copy
import http.client
import json
import os
from pathlib import Path
import time
import urllib.request
import zipfile
from unittest.mock import patch

import pytest
from baseball_lab.web.storage import Storage
from baseball_lab.data.protection import public_view,public_text
from baseball_lab.data.lineage import write_json
from baseball_lab.r1.provider import download,extract_csv,OfficialRedirect
from test_web import web,call


def fixture_collection(root):
    target=root/'outputs/workbench/MOCK_TEST_ONLY'
    target.mkdir(parents=True)
    (target/'mock.log').write_text('MOCK_TEST_ONLY')
    return target


def test_delete_requires_preview_consent_and_unchanged_target(tmp_path):
    target=fixture_collection(tmp_path);store=Storage(tmp_path)
    preview=store.preview('run:MOCK_TEST_ONLY')
    with pytest.raises(ValueError):store.delete(preview['confirmation'],False)
    assert target.exists()
    (target/'mock.log').write_text('changed mock')
    with pytest.raises(ValueError,match='변경'):store.delete(preview['confirmation'],True)
    assert target.exists()
    fresh=store.preview('run:MOCK_TEST_ONLY');store.delete(fresh['confirmation'],True)
    assert not target.exists()
    with pytest.raises(ValueError):store.delete(fresh['confirmation'],True)


def test_expiry_and_fixed_target_ids(tmp_path):
    target=fixture_collection(tmp_path);store=Storage(tmp_path)
    with pytest.raises(ValueError):store.preview('../../')
    preview=store.preview('run:MOCK_TEST_ONLY')
    with patch('baseball_lab.web.storage.time.monotonic',return_value=time.monotonic()+200):
        with pytest.raises(ValueError,match='만료'):store.delete(preview['confirmation'],True)
    assert target.exists()


@pytest.mark.skipif(os.name!='posix',reason='POSIX symlink and permission checks')
def test_symlink_collections_and_json_temporary_file_cannot_escape(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();victim=outside/'private.txt';victim.write_text('KEEP')
    root=tmp_path/'app';parent=root/'outputs/workbench';parent.mkdir(parents=True)
    (parent/'linked').symlink_to(outside,target_is_directory=True)
    store=Storage(root)
    with pytest.raises(ValueError):store.preview('run:linked')
    assert victim.read_text()=='KEEP'
    target=fixture_collection(root);(target/'link').symlink_to(victim)
    with pytest.raises(ValueError):store.preview('run:MOCK_TEST_ONLY')
    file=tmp_path/'data.json';file.with_suffix('.json.tmp').symlink_to(victim)
    with pytest.raises(OSError):write_json(file,{'would':'overwrite'})
    assert victim.read_text()=='KEEP'
    (tmp_path/'safe').mkdir();write_json(tmp_path/'safe/value.json',{'safe':True})
    assert (tmp_path/'safe/value.json').stat().st_mode & 0o777==0o600


def test_inventory_classification_dependencies_no_absolute_paths(tmp_path):
    source=tmp_path/'data/local/retrosheet/official-2024';source.mkdir(parents=True)
    (source/'2024plays.zip').write_bytes(b'MOCK')
    target=fixture_collection(tmp_path);(target/'result').mkdir()
    write_json(target/'result/research.json',{'model':{'selected_dates':['2024-03-20','2024-09-30']}})
    inv=Storage(tmp_path).inventory();item=next(i for i in inv['items'] if i['id']=='source:2024')
    assert item['dependent_runs']==1 and item['bytes']==4
    assert not Path(item['location']).is_absolute()
    assert inv['encrypted_by_app'] is False and inv['local_only'] is True
    assert len(inv['categories'])>=6


def test_views_redact_sensitive_material_and_leave_lineage_unchanged():
    data={'path':'/home/alice/private.csv','parsed_csv_path':'C:\\Users\\Alice\\secret.csv',
          'provider':'official','error':'failed /workspace/private.csv token=abc123', 'token':'private-value'}
    old=copy.deepcopy(data);view=public_view(data)
    assert data==old
    assert 'alice' not in json.dumps(view).lower() and 'abc123' not in json.dumps(view)
    assert 'token' not in view and 'path' not in view
    assert 'test-key' not in public_text('api_key=test-key password=123')
    assert 'alice' not in public_text('https://alice:private@example.test/path')


@pytest.mark.parametrize('member',['../escape.csv','/absolute.csv','folder/2024plays.csv'])
def test_zip_members_cannot_escape(tmp_path,member):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(member,'bad')
    with pytest.raises(ValueError):extract_csv(archive,tmp_path/'output.csv',2024)
    assert not (tmp_path/'output.csv').exists()


def test_zip_bomb_duplicate_and_success(tmp_path):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('2024plays.csv','x'*100000)
    with pytest.raises(ValueError,match='압축률'):extract_csv(archive,tmp_path/'output.csv',2024)
    with zipfile.ZipFile(archive,'w') as z:z.writestr('2024plays.csv','a,b\n1,2\n')
    extract_csv(archive,tmp_path/'output.csv',2024)
    assert (tmp_path/'output.csv').read_text()=='a,b\n1,2\n'


def test_download_rejects_unregistered_urls_and_external_redirect(tmp_path):
    with patch('urllib.request.build_opener') as opener:
        with pytest.raises(ValueError):download('https://127.0.0.1/private',tmp_path/'a',100)
        opener.assert_not_called()
    redirect=OfficialRedirect();request=urllib.request.Request('https://www.retrosheet.org/downloads/plays.html')
    for url in ('http://www.retrosheet.org/a','https://localhost/a','https://www.retrosheet.org:8443/a','https://secret@www.retrosheet.org/a'):
        with pytest.raises(ValueError):redirect.redirect_request(request,None,302,'',{},url)


def test_storage_http_security_and_explicit_confirmation(web):
    wb,server=web;target=fixture_collection(wb.root)
    headers={'X-Lab-Token':wb.token}
    assert call(server,'/api/storage/preview','POST','{}')[0]==403
    assert call(server,'/api/storage/preview','POST',json.dumps({'id':'run:MOCK_TEST_ONLY'}),headers|{'Origin':'https://evil.test'})[0]==403
    code,body=call(server,'/api/storage/preview','POST',json.dumps({'id':'run:MOCK_TEST_ONLY'}),headers)
    assert code==200;nonce=json.loads(body)['confirmation']
    assert call(server,'/api/storage/delete','POST',json.dumps({'confirmation':nonce}),headers)[0]==400
    assert target.exists()
    code,_=call(server,'/api/storage/delete','POST',json.dumps({'confirmation':nonce,'confirmed':True}),headers)
    assert code==200 and not target.exists()
    wb.job={'status':'running'}
    assert call(server,'/api/storage/preview','POST',json.dumps({'id':'source:2024'}),headers)[0]==400


def test_response_security_headers(web):
    wb,server=web;connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
    connection.request('GET','/');response=connection.getresponse()
    assert response.getheader('X-Content-Type-Options')=='nosniff'
    assert "frame-ancestors 'none'" in response.getheader('Content-Security-Policy')
    assert response.getheader('Referrer-Policy')=='no-referrer'
    connection.close()


def test_cached_source_version_cannot_bypass_registered_release(tmp_path):
    from baseball_lab.r1.provider import acquire
    from baseball_lab.data.retrosheet_releases import RELEASES
    target=tmp_path/'official-2024';target.mkdir();(target/'dataset.json').write_text('{}')
    with patch('baseball_lab.r1.provider.load',return_value={'manifest':{'source_version':RELEASES[2024]['sha256']}}),patch('baseball_lab.r1.provider.checksum',return_value='changed'),patch('baseball_lab.r1.provider.download') as network:
        with pytest.raises(ValueError,match='공식 배포'):acquire(tmp_path)
        network.assert_not_called()


def test_upload_limits_and_credential_url_rejection(web):
    wb,server=web;headers={'X-Lab-Token':wb.token,'Content-Length':str(33*1024*1024)}
    assert call(server,'/api/upload','POST',b'x',headers)[0]==400
    from baseball_lab.data.statcast import manual_source
    with pytest.raises(ValueError):manual_source(Path('not-read.csv'),'https://user:password@baseballsavant.mlb.com/export','local use','2026-11-05T00:00:00+09:00')


def test_legacy_log_display_is_redacted_without_modifying_original(web):
    wb,server=web;directory=wb.outputs/'legacy';directory.mkdir()
    text='failed /home/alice/private.csv token=old-secret\n'
    (directory/'output.log').write_text(text)
    code,body=call(server,'/reports/legacy/output.log')
    assert code==200 and b'alice' not in body and b'old-secret' not in body
    assert (directory/'output.log').read_text()==text
