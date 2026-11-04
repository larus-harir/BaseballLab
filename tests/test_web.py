import http.client
import json
from pathlib import Path
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest
from baseball_lab.web.server import Workbench,make_handler


@pytest.fixture
def web(tmp_path):
    wb=Workbench(tmp_path)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(wb))
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    yield wb,server
    server.shutdown();server.server_close();t.join()


def call(server,path='/',method='GET',data=None,headers=None):
    c=http.client.HTTPConnection('127.0.0.1',server.server_port)
    c.request(method,path,body=data,headers=headers or {})
    r=c.getresponse();body=r.read();c.close()
    return r.status,body


def test_home_state_and_training_blocked_without_data(web):
    wb,s=web
    code,body=call(s)
    assert code==200 and '학습 시작' in body.decode() and wb.token in body.decode()
    code,body=call(s,'/api/state')
    assert not json.loads(body)['readiness']['ready']
    code,body=call(s,'/api/start','POST',json.dumps({'kind':'train'}),{'X-Lab-Token':wb.token})
    assert code==400
    assert not list(wb.outputs.glob('*/task.json'))


def test_token_origin_host_and_traversal(web):
    wb,s=web
    assert call(s,'/api/start','POST','{}')[0]==403
    assert call(s,'/api/start','POST','[]',{'X-Lab-Token':wb.token})[0]==400
    assert call(s,'/api/start','POST',json.dumps({'kind':'fit','options':None}),{'X-Lab-Token':wb.token})[0]==400
    assert call(s,'/api/start','POST','{}',{'X-Lab-Token':wb.token,'Origin':'https://untrusted.example'})[0]==403
    assert call(s,'/',headers={'Host':'untrusted.example'})[0]==403
    assert call(s,'/reports/%2e%2e/%2e%2e/secrets/report.html')[0]==403
    assert call(s,'/reports/job/result/research.json')[0]==403


def test_no_shell_task_injection_and_strict_options(tmp_path):
    w=Workbench(tmp_path)
    with pytest.raises(ValueError):w.start('shell',{'command':'rm'})
    with pytest.raises(ValueError):w.start('fit',{'train_before':'2024-05-06','test_from':'2024-05-01'})
    with patch.object(w,'readiness',return_value={'ready':True}):
        for episodes in ('600; echo injected',True,0,100001):
            with pytest.raises(ValueError):w.start('train',{'episodes':episodes})


def test_upload_rejects_non_csv_and_missing_source(web):
    wb,s=web
    assert call(s,'/api/upload','POST',b'not a zip',{'X-Lab-Token':wb.token,'X-Filename':'code.zip'})[0]==400
    assert call(s,'/api/upload','POST',b'x,y',{'X-Lab-Token':wb.token,'X-Filename':'export.csv'})[0]==400
    assert not list(wb.data.rglob('*.csv'))


def test_worker_records_failure_and_cancel_serializes(tmp_path):
    w=Workbench(tmp_path)
    w.data.mkdir(parents=True);(w.data/'dataset.json').write_text('{}')
    # Running the existing fixed CLI without a repository path fails honestly; no fake success.
    w.start('fit',{'train_before':'2024-05-04','test_from':'2024-05-05'})
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if w.state()['job']['status']=='failed':break
        time.sleep(.02)
    assert w.state()['job']['status']=='failed'
    assert w.state()['job']['exit_code']!=0
    with w.lock:
        w.job.update(status='running')
    with pytest.raises(ValueError,match='작업 중'):w.start('fit',{})
    assert w.cancel()['message']
    assert w.job['status']=='cancelling'


def test_stale_jobs_are_not_shown_as_running_after_restart(tmp_path):
    w=Workbench(tmp_path)
    (w.outputs/'old').mkdir()
    (w.outputs/'old/task.json').write_text(json.dumps({'id':'old','status':'running','logs':[]}))
    assert w.state()['runs'][0]['status']=='interrupted'


def test_real_process_cancel_and_progress_are_recorded(tmp_path):
    import subprocess,sys
    original=subprocess.Popen
    w=Workbench(tmp_path)
    w.data.mkdir(parents=True);(w.data/'dataset.json').write_text('{}')
    def controlled_process(command,**kwargs):
        assert isinstance(command,list) and '--mode' in command
        return original([sys.executable,'-u','-c',"import time;print('MOCK_TEST_ONLY 학습 8/24타석',flush=True);time.sleep(10)"],**kwargs)
    with patch('baseball_lab.web.server.subprocess.Popen',side_effect=controlled_process), patch.object(w,'readiness',return_value={'ready':True}):
        w.start('train',{'episodes':24,'seed':41})
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            state=w.state()['job']
            if state.get('completed_episodes')==8:break
            time.sleep(.02)
        assert state.get('completed_episodes')==8
        w.cancel()
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            state=w.state()['job']
            if state['status']=='cancelled':break
            time.sleep(.02)
        assert state['status']=='cancelled'
        assert 'MOCK_TEST_ONLY' in state['logs'][0]


def test_platform_match_and_observer_are_separate_pages(web):
    wb,s=web
    for path,label in [('/','무엇을 해볼까요?'),('/match','BaseballLab-Match'),('/match/team','한 점을 만들고 막는'),('/match/at-bat','researchSource'),('/simulation','학습 없이 관찰'),('/lab/data','어떤 자료')]:
        code,body=call(s,path)
        assert code==200 and label in body.decode()
    with pytest.raises(ValueError):wb.start('simulate',{'start':'2024-03-20','end':'2024-09-30','outs':3})


def test_old_r1_result_is_summarized_without_overwriting_original(web):
    wb,s=web
    data=json.loads((Path(__file__).parents[1]/'docs/results/e01-r1-2024.json').read_text())
    output=wb.outputs/'old/result';output.mkdir(parents=True)
    source=json.dumps(data);(output/'research.json').write_text(source)
    (output/'report.html').write_text('LEGACY_UNCHANGED')
    code,body=call(s,'/reports/old/result/report.html')
    assert code==200 and '이번 조건에서는 수비 쪽 우세' in body.decode()
    assert (output/'report.html').read_text()=='LEGACY_UNCHANGED'
    assert (output/'research.json').read_text()==source
