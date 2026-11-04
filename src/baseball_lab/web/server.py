"""Loopback-only research workbench. Fixed task API, no shell commands from clients."""
import argparse
import json
import mimetypes
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from baseball_lab.data.lineage import write_json, utc_now


class Workbench:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.data=self.root/'data/local/statcast'
        self.outputs=self.root/'outputs/workbench'
        self.outputs.mkdir(parents=True,exist_ok=True)
        self.token=secrets.token_urlsafe(32)
        self.lock=threading.RLock()
        self.job=None; self.process=None
        self._cache=(0,None)

    def readiness(self, refresh=False):
        now=time.monotonic()
        if not refresh and self._cache[1] is not None and now-self._cache[0]<5:
            return self._cache[1]
        result={'ready':False,'title':'기간을 고르고 AI 학습을 시작하세요','reason':'확인된 보관 자료를 먼저 찾습니다. 없으면 자동 수집이 허용된 자료 연결이 필요합니다.',
                'model_id':None,'dataset':None,'issues':[],'warning':'현재 학습은 타석 출루 연습입니다. 경기 승리 학습이 아닙니다.'}
        try:
            quality=self.data/'quality.json'
            if quality.exists():
                q=json.loads(quality.read_text(encoding='utf-8'))
                result['dataset']={'rows':q['used_rows'],'raw_rows':q['raw_rows'],'games':q['games'],
                                   'dates':q['date_range'],'status':q['source_status'],
                                   'missingness':q['missingness_report'],'exclusions':q['exclusions']}
            model_path=self.data/'model.json'
            if model_path.exists():
                from baseball_lab.outcome.empirical import load_model
                model,dataset=load_model(model_path)
                v=model.artifact['validation']
                result.update({'ready':True,'title':'제한된 타석 학습을 시작할 수 있어요',
                    'reason':'원본 파일과 분리된 검증 기간을 확인했습니다. 선수 능력이나 인과효과가 입증됐다는 뜻은 아닙니다.',
                    'model_id':model.artifact['model_id'],'validation':v,'split':model.artifact['split']})
        except (OSError,ValueError,KeyError,TypeError) as exc:
            result.update({'title':'자료나 모델을 다시 확인해야 해요','reason':str(exc),'issues':[str(exc)]})
        self._cache=(now,result)
        return result

    def state(self):
        with self.lock:
            current=dict(self.job) if self.job else None
            if current:current['logs']=list(current['logs'])
        runs=[]
        for p in sorted(self.outputs.glob('*/task.json'),reverse=True)[:30]:
            try:
                run=json.loads(p.read_text(encoding='utf-8'))
                if run['status'] in ('queued','running') and (not current or run['id']!=current['id']):
                    run['status']='interrupted'
                run.pop('logs',None);runs.append(run)
            except (OSError,ValueError,KeyError):continue
        return {'readiness':self.readiness(),'job':current,'runs':runs}

    def _idle(self):
        if self.job and self.job['status'] in ('queued','running','cancelling'):
            raise ValueError('이미 작업 중입니다. 끝날 때까지 기다리거나 중지해 주세요.')

    def upload(self, filename, content, source_url, acquired_at, usage_note):
        with self.lock:
            self._idle()
            if not filename.lower().endswith('.csv') or len(content)>32*1024*1024:
                raise ValueError('CSV 파일 한 개는 최대 32MB입니다.')
            from baseball_lab.data.statcast import manual_source, audit
            # The browser filename is informational only; never use it as a server path.
            directory=self.data/'uploads'/secrets.token_hex(8)
            directory.mkdir(parents=True)
            path=directory/'official-export.csv';path.write_bytes(content)
            try:
                source=manual_source(path,source_url,usage_note,acquired_at)
                dataset=audit([source],self.data)
            except Exception:
                path.unlink(missing_ok=True);directory.rmdir();raise
            self._cache=(0,None)
            return {'rows':dataset['manifest']['used_rows'],'date_range':dataset['manifest']['date_range'],
                    'message':'파일 확인 완료. 날짜를 나누고 모델 검사를 진행하세요.'}

    def start(self, kind, options):
        with self.lock:
            self._idle()
            from datetime import date
            if not isinstance(options,dict):raise ValueError('작업 설정은 객체여야 합니다.')
            if kind not in ('fit','train','run'):raise ValueError('지원하지 않는 작업')
            if kind=='run':
                from baseball_lab.research.pipeline import Plan
                plan=Plan(str(options.get('start','')),str(options.get('end','')))
                episodes=options.get('episodes',600);seed=options.get('seed',20261104)
                if type(episodes) is not int or not 20<=episodes<=100000:raise ValueError('학습 타석 수는 20~100,000 사이의 정수입니다.')
                if type(seed) is not int or not 0<=seed<=2**31-1:raise ValueError('재현 번호 범위를 확인하세요.')
                extra=['--mode','run','--start',plan.start,'--end',plan.end,'--episodes',str(episodes),'--seed',str(seed)]
                reference=options.get('authorization_reference','')
                if not isinstance(reference,str) or len(reference)>2000:raise ValueError('자료 연결 설정을 확인하세요.')
                if reference.strip():extra.extend(['--authorization-reference',reference.strip()])
            elif kind=='fit':
                before=date.fromisoformat(str(options.get('train_before','')))
                after=date.fromisoformat(str(options.get('test_from','')))
                if before>=after:raise ValueError('검증 시작일은 최종 확인 시작일보다 빨라야 합니다.')
                if not (self.data/'dataset.json').exists():raise ValueError('먼저 공식 CSV를 올려 주세요.')
                extra=['--mode','fit','--train-before',str(before),'--test-from',str(after)]
            else:
                ready=self.readiness(refresh=True)
                if not ready['ready']:raise ValueError(ready['reason'])
                episodes=options.get('episodes',600);seed=options.get('seed',20261104)
                if type(episodes) is not int or not 20<=episodes<=100000:raise ValueError('학습 타석 수는 20~100,000 사이의 정수로 입력하세요.')
                if type(seed) is not int or not 0<=seed<=2**31-1:raise ValueError('재현 번호는 0~2,147,483,647 사이의 정수입니다.')
                extra=['--mode','train','--episodes',str(episodes),'--seed',str(seed),'--evaluate-every',str(min(episodes,200))]
            job_id=time.strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)
            output=self.outputs/job_id;output.mkdir()
            self.job={'id':job_id,'kind':kind,'status':'queued','started_at':utc_now(),'logs':[],
                      'report':None,'message':'작업을 준비하고 있어요.'}
            self._persist()
            command=[sys.executable,'-u',str(self.root/'scripts/quickstart.py'),'--data-dir',str(self.data),
                     '--output',str(output/'result'),*extra]
            threading.Thread(target=self._worker,args=(job_id,command,output),daemon=True).start()
            return {'id':job_id}

    def _persist(self):
        write_json(self.outputs/self.job['id']/'task.json',self.job)

    def _worker(self,job_id,command,output):
        process=None
        try:
            with self.lock:
                if self.job['status']=='cancelling':
                    self.job.update(status='cancelled',message='작업을 중지했습니다.');self._persist();return
                env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1'}
                process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                         cwd=self.root,env=env,text=True,encoding='utf-8',errors='replace')
                self.process=process
                self.job.update(status='running',message='자료 준비부터 순서대로 진행하고 있어요.' if self.job['kind']=='run' else '기록을 검사하고 있어요.' if self.job['kind']=='fit' else '두 AI가 타석 대결을 학습하고 있어요.')
                self._persist()
            with (output/'output.log').open('w',encoding='utf-8') as log:
                for line in process.stdout:
                    log.write(line);log.flush()
                    with self.lock:
                        self.job['logs'].append(line.rstrip())
                        progress=re.search(r'학습 (\d+)/(\d+)타석',line)
                        if line.startswith('단계 '):self.job['message']=line.strip()
                        if progress and self.job['kind'] in ('train','run'):
                            done,total=map(int,progress.groups())
                            self.job.update(completed_episodes=done,target_episodes=total,message=f'학습 {done:,}/{total:,}타석 · 현재까지의 결과를 볼 수 있어요.')
                        if (output/'result/report.html').exists():
                            self.job['report']=f'/reports/{job_id}/result/report.html'
                        self.job['logs']=self.job['logs'][-120:]
                        self._persist()
            code=process.wait()
            with self.lock:
                cancelled=self.job['status']=='cancelling'
                self._cache=(0,None)
                invalid_fit=self.job['kind']=='fit' and code==0 and not self.readiness(refresh=True)['ready']
                status='cancelled' if cancelled else 'failed' if code or invalid_fit else 'completed'
                message='작업을 중지했습니다.' if cancelled else '검사를 통과하지 못했어요. 아래 이유를 확인하세요.' if invalid_fit else '문제가 생겼어요. 아래 기록과 도움말을 확인하세요.' if code else '완료했어요. 결과 보기를 눌러 주세요.'
                report=output/'result/report.html'
                failure=output/'result/failure.json'
                if failure.exists() and not cancelled:
                    try:message=json.loads(failure.read_text(encoding='utf-8'))['error']
                    except (OSError,ValueError,KeyError):pass
                self.job.update(status=status,message=message,exit_code=code,completed_at=utc_now(),
                    report=f'/reports/{job_id}/result/report.html' if report.exists() else None)
                self._persist()
        except Exception as exc:
            if process and process.poll() is None:process.terminate();process.wait(timeout=10)
            with self.lock:
                self.job.update(status='failed',message=str(exc),completed_at=utc_now());self._persist()
        finally:
            with self.lock:
                if self.process is process:self.process=None

    def cancel(self):
        with self.lock:
            if not self.job or self.job['status'] not in ('queued','running'):raise ValueError('중지할 작업이 없습니다.')
            self.job.update(status='cancelling',message='중지하는 중입니다. 현재 작업 기록은 남겨 둡니다.');self._persist()
            if self.process and self.process.poll() is None:self.process.terminate()
            return {'message':'중지를 요청했습니다.'}


def make_handler(workbench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def _host_ok(self):
            host=self.headers.get('Host','')
            port=self.server.server_port
            return host in (f'127.0.0.1:{port}',f'localhost:{port}')
        def _json(self,payload,status=200):
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def _file(self,path):
            try:body=path.read_bytes()
            except OSError:return self._json({'error':'파일이 없어요.'},404)
            self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if not self._host_ok():return self._json({'error':'로컬 주소로 접속하세요.'},403)
            path=urlparse(self.path).path
            if path=='/':
                body=Path(__file__).with_name('workbench.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__',workbench.token).encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
            elif path=='/api/state':self._json(workbench.state())
            elif path.startswith('/reports/'):
                from urllib.parse import unquote
                resolved=(workbench.outputs/unquote(path[len('/reports/'):])).resolve()
                if not resolved.is_relative_to(workbench.outputs.resolve()) or resolved.name not in ('report.html','summary.md','output.log'):
                    return self._json({'error':'허용하지 않는 경로'},403)
                self._file(resolved)
            else:self._json({'error':'페이지가 없어요.'},404)
        def do_POST(self):
            if not self._host_ok() or self.headers.get('X-Lab-Token')!=workbench.token:
                return self._json({'error':'이 창을 새로고침해 주세요.'},403)
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                return self._json({'error':'다른 사이트의 실행 요청을 허용하지 않습니다.'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32*1024*1024:raise ValueError('파일 또는 요청 크기는 최대 32MB입니다.')
                body=self.rfile.read(length)
                if len(body)!=length:raise ValueError('전송이 끝나지 않았어요.')
                path=urlparse(self.path).path
                if path=='/api/upload':
                    from urllib.parse import unquote
                    result=workbench.upload(unquote(self.headers.get('X-Filename','export.csv')),body,
                        unquote(self.headers.get('X-Source-URL','')),unquote(self.headers.get('X-Acquired-At','')),
                        unquote(self.headers.get('X-Usage-Note','')))
                elif path=='/api/start':
                    payload=json.loads(body)
                    if not isinstance(payload,dict):raise ValueError('올바른 작업 요청이 아닙니다.')
                    result=workbench.start(payload['kind'],payload.get('options',{}))
                elif path=='/api/cancel':result=workbench.cancel()
                else:return self._json({'error':'지원하지 않는 요청'},404)
                self._json(result)
            except (ValueError,KeyError,TypeError,OSError) as exc:self._json({'error':str(exc)},400)
    return Handler


def serve(root,port=8765,open_browser=False):
    workbench=Workbench(root)
    server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(workbench))
    server.daemon_threads=True
    address=f'http://127.0.0.1:{server.server_port}'
    print('야구 AI 연구실을 열었습니다: '+address,flush=True)
    print('브라우저에서 자료 준비 → 모델 검사 → 학습 → 결과 보기를 진행하세요. 종료: Ctrl+C',flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(.3,lambda:webbrowser.open(address)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        with workbench.lock:
            if workbench.process and workbench.process.poll() is None:
                workbench.job.update(status='cancelling',message='연구실 종료로 중지했습니다.');workbench._persist();workbench.process.terminate()
        server.server_close()
