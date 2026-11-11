"""Acceptance boundaries for automatic data preparation.

Fixtures and forced failures are MOCK_TEST_ONLY and stay in pytest temp roots.
"""
import hashlib
import http.client
import json
import threading
import time
from unittest.mock import patch

from test_web import web
from test_matchup import mock_catalog


def request(server, path, payload=None, *, token=None, origin=None, raw=None, host=None):
    headers={}
    if token is not None:headers['X-Lab-Token']=token
    if origin is not None:headers['Origin']=origin
    if host is not None:headers['Host']=host
    body=raw if raw is not None else None if payload is None else json.dumps(payload)
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=4)
    connection.request('GET' if body is None else 'POST',path,body=body,headers=headers)
    response=connection.getresponse();data=response.read();connection.close()
    return response.status,json.loads(data)


def terminal(server,timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        _,state=request(server,'/api/state?project=baseball')
        if state.get('job',{}).get('status') in ('completed','failed','cancelled'):return state['job']
        time.sleep(.02)
    raise AssertionError('MOCK_TEST_ONLY preparation did not finish')


def test_prepare_rejects_untrusted_or_ambiguous_requests_before_scheduling(web):
    wb,server=web
    valid={'project':'baseball','season':2024}
    assert request(server,'/api/matchup/prepare',valid)[0]==403
    assert request(server,'/api/matchup/prepare',valid,token=wb.token,origin='null')[0]==403
    assert request(server,'/api/matchup/prepare',valid,token=wb.token,host='untrusted.example')[0]==403
    for body in ('[]','null','42','"project"','not JSON'):
        assert request(server,'/api/matchup/prepare',token=wb.token,raw=body)[0]==400
    for payload in ({'project':[],'season':2024}, {'project':'../../etc','season':2024},
                    {'project':'baseball','season':'2024; curl untrusted'},
                    {'project':'baseball','season':True}, {'project':'baseball','season':2024.5},
                    {'project':'baseball','season':1900}):
        assert request(server,'/api/matchup/prepare',payload,token=wb.token)[0]==400
    assert wb.job is None
    assert not list(wb.outputs.glob('*/task.json'))


def test_preparation_does_not_block_state_or_allow_competing_mutations(web):
    wb,server=web;entered=threading.Event();release=threading.Event()
    def wait_for_provider(self,project,season=2024,progress=None):
        if progress:progress('MOCK_TEST_ONLY 선수 기록 확인')
        entered.set();release.wait(4)
        raise OSError('MOCK_TEST_ONLY network unavailable')
    with patch('baseball_lab.data.catalog.DatasetCatalog.ensure',wait_for_provider):
        try:
            status,queued=request(server,'/api/matchup/prepare',{'project':'baseball','season':2024},token=wb.token)
            assert status==200 and queued.get('id')
            assert entered.wait(2)
            began=time.monotonic();status,state=request(server,'/api/state?project=baseball')
            assert status==200 and time.monotonic()-began<1.5
            assert state['job']['kind']=='prepare_catalog' and state['job']['status'] in ('queued','running')
            assert request(server,'/api/start',{'kind':'fit','options':{}},token=wb.token)[0]==400
            assert request(server,'/api/storage/preview',{'id':'catalog:mlb-2024'},token=wb.token)[0]==400
            assert request(server,'/api/matchup/analyze',{'project':'baseball','options':{}},token=wb.token)[0]==400
            assert request(server,'/api/cancel',{},token=wb.token)[0]==200
        finally:release.set()
        finished=terminal(server)
    assert finished['status']=='cancelled'
    assert not list(wb.outputs.glob('*/result/analysis.json'))


def test_failed_provider_exposes_a_retryable_failure_without_fake_success(web):
    wb,server=web
    failure=OSError('MOCK_TEST_ONLY offline /tmp/private/records.csv token=MOCK_TEST_ONLY_SECRET')
    with patch('baseball_lab.data.catalog.DatasetCatalog.ensure',side_effect=failure):
        status,queued=request(server,'/api/matchup/prepare',{'project':'baseball','season':2024},token=wb.token)
        assert status==200 and queued.get('id')
        job=terminal(server)
    assert job['status']=='failed' and not job.get('report')
    assert 'MOCK_TEST_ONLY_SECRET' not in job['message'] and '/tmp/private' not in job['message']
    status,overview=request(server,'/api/matchup/catalog?project=baseball&season=2024')
    assert status==200 and overview['ready'] is False
    assert not overview.get('profiles')
    assert not list(wb.outputs.glob('*/result/analysis.json'))


def test_linked_assignment_is_reused_offline_without_rewriting(web,mock_catalog):
    wb,server=web;root,_=mock_catalog
    assert root==wb.root
    catalog=root/'data/local/catalog/kbo-assignment/catalog.json';before=catalog.read_bytes()
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('MOCK_TEST_ONLY no network expected')):
        status,_=request(server,'/api/matchup/prepare',{'project':'eramatch','season':1982},token=wb.token)
        assert status==200
        # A cached request can complete immediately or through the same small job.
        if wb.job:terminal(server)
        status,data=request(server,'/api/matchup/catalog?project=eramatch&season=1982')
    assert status==200 and data['ready']
    assert catalog.read_bytes()==before
    # Only the fixture's recognized hash is substituted, never a production pin.
    content=b'MOCK_TEST_ONLY already connected archive'
    with patch('baseball_lab.matchup.catalog.LEGACY_SHA',hashlib.sha256(content).hexdigest()):
        assert request(server,'/api/matchup/import',token=wb.token,raw=content)[0]==200
    assert catalog.read_bytes()==before
