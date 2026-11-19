"""MOCK_TEST_ONLY failed diagnostics must not masquerade as learning results."""
import io
import json
from unittest.mock import patch
import pytest
from baseball_lab.web.server import Workbench
from baseball_lab.data.lineage import write_json
from test_web import web,call


OPTIONS={'source':'retrosheet','study':'pitch_game','start':'2025-03-18','end':'2025-09-28',
         'collected_window':True,'episodes':20,'seed':41}


def failed_job(wb):
    with patch('threading.Thread.start'):
        result=wb.start('run',OPTIONS)
    output=wb.outputs/result['id'];report=output/'result/report.html'
    write_json(output/'result/failure.json',{'error':'MOCK_TEST_ONLY handshake timeout'})
    report.write_text('MOCK_TEST_ONLY diagnostic',encoding='utf-8')
    class Failed:
        stdout=io.StringIO('MOCK_TEST_ONLY connection reset\n')
        def wait(self,*args,**kwargs):return 2
        def poll(self):return 2
    with patch('subprocess.Popen',return_value=Failed()):wb._worker(result['id'],['MOCK_TEST_ONLY'],output)
    return result['id']


def test_failed_job_has_no_result_and_retries_original_settings_after_restart(tmp_path):
    wb=Workbench(tmp_path);job_id=failed_job(wb)
    state=wb.state('match')
    assert state['job']['report'] is None and state['job']['can_retry']
    assert state['runs'][0]['report'] is None and state['runs'][0]['can_retry']
    assert 'retry_request' not in state['runs'][0]
    original=(wb.outputs/job_id/'task.json').read_bytes()
    resumed=Workbench(tmp_path)
    with patch('threading.Thread.start'):
        next_job=resumed.retry(job_id)
    assert next_job['id']!=job_id
    assert resumed.job['retry_request']=={'kind':'run','options':OPTIONS}
    assert (wb.outputs/job_id/'task.json').read_bytes()==original


def test_legacy_failed_report_is_hidden_without_rewriting_history(tmp_path):
    wb=Workbench(tmp_path);folder=wb.outputs/'MOCK_TEST_ONLY_old'
    write_json(folder/'task.json',{'id':folder.name,'kind':'run','status':'failed',
        'started_at':'2000-01-01','report':'/reports/MOCK_TEST_ONLY_old/result/report.html'})
    before=(folder/'task.json').read_bytes()
    run=wb.state('match')['runs'][0]
    assert run['report'] is None and not run['can_retry']
    assert (folder/'task.json').read_bytes()==before


def test_retry_http_preserves_csrf_host_and_path_guards(web):
    wb,server=web;job_id=failed_job(wb)
    code,_=call(server,'/api/retry','POST',json.dumps({'id':job_id}))
    assert code==403
    for job in ('../MOCK_TEST_ONLY','/tmp/MOCK_TEST_ONLY'):
        code,_=call(server,'/api/retry','POST',json.dumps({'id':job}),{'X-Lab-Token':wb.token})
        assert code==400
    with patch.object(wb,'start',return_value={'id':'MOCK_TEST_ONLY_retry'}) as start:
        code,body=call(server,'/api/retry','POST',json.dumps({'id':job_id}),{'X-Lab-Token':wb.token})
    assert code==200 and json.loads(body)['id']!=job_id
    start.assert_called_once_with('run',OPTIONS)
