"""Loopback-only research workbench. Fixed task API, no shell commands from clients."""
import argparse
import csv
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
from urllib.parse import urlparse,parse_qs

from baseball_lab.data.lineage import write_json, utc_now
from baseball_lab.data.protection import private,public_text,public_view
from .storage import Storage


class PreparationCancelled(Exception):
    """Cooperative cancellation between bounded data-provider operations."""


class Workbench:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.data=self.root/'data/local/statcast'
        self.outputs=self.root/'outputs/workbench'
        private(self.root/'outputs',directory=True)
        private(self.outputs,directory=True)
        private(self.root/'data/local',directory=True)
        self.storage=Storage(self.root)
        from baseball_lab.data.catalog import DatasetCatalog
        self.catalog=DatasetCatalog(self.root)
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
        # This provider can prepare its public distribution on the first run;
        # a missing cache is not a request for users to find/upload a CSV.
        result['scoring']={'available':True,'cached':(self.root/'data/local/retrosheet/official-2024/dataset.json').exists(),
                           'title':'실제 Retrosheet 기록으로 득점 상황 학습',
                           'reason':'선택한 시즌의 공식 배포 자료를 자동 준비하고 재사용합니다. 처음 받을 때만 인터넷이 필요합니다.'}
        return result

    def state(self,project=None):
        if project not in (None,'match','baseball','eramatch'):raise ValueError('프로젝트를 확인하세요.')
        with self.lock:
            current=dict(self.job) if self.job else None
            if current:current['logs']=list(current['logs'])
        runs=[]
        for p in sorted(self.outputs.glob('*/task.json'),reverse=True):
            try:
                run=json.loads(p.read_text(encoding='utf-8'))
                if project=='match' and run.get('kind') in ('matchup','prepare_catalog'):continue
                if project in ('baseball','eramatch') and (run.get('kind')!='matchup' or run.get('project')!=project):continue
                if run['status'] in ('queued','running','cancelling') and (not current or run['id']!=current['id']):
                    run['status']='interrupted'
                run.pop('logs',None);runs.append(run)
                evidence=p.parent/'result/research.json'
                if evidence.exists():
                    data=json.loads(evidence.read_text(encoding='utf-8'))
                    if data.get('schema')=='E01-R1-research-v1':
                        from baseball_lab.experiments.match.reporting.summary import build_summary
                        reading=build_summary(data)
                        run['reading']={k:reading[k] for k in ('headline','growth_headline','complete')}
                    elif data.get('schema')=='Match-half-inning-research-v1':
                        from baseball_lab.experiments.match.reporting.inning import summary
                        reading=summary(data)
                        run['reading']={k:reading[k] for k in ('headline','growth_headline','complete')}
                if len(runs)>=30:break
            except (OSError,ValueError,KeyError):continue
        return public_view({'readiness':self.readiness(),'job':current,'runs':runs})

    def _idle(self):
        if self.job and self.job['status'] in ('queued','running','cancelling'):
            raise ValueError('이미 작업 중입니다. 끝날 때까지 기다리거나 중지해 주세요.')

    def matchup_prepare(self, archive=None, *, project='baseball',season=2024):
        with self.lock:
            from baseball_lab.matchup.service import PROJECTS
            if not isinstance(project,str) or project not in PROJECTS:
                raise ValueError('선수 대결 또는 역대 선수 대결을 선택하세요.')
            if archive is not None:
                self._idle()
                from baseball_lab.matchup.catalog import import_assignment
                result=import_assignment(self.root,archive)
                return {'ready':True,'status':'completed','dataset_id':result['dataset_id'],
                        'message':'보관한 과제 기록을 연결했습니다.'}
            # Validate requested season before scheduling or creating any files.
            self.catalog.source_id(project,season)
            if self.job and self.job.get('kind')=='prepare_catalog' and self.job.get('project')==project and self.job.get('season')==season and self.job['status'] in ('queued','running'):
                return {'id':self.job['id'],'status':self.job['status'],'ready':False,'reused':True}
            self._idle()
            existing=self.catalog.get(project,season)
            if existing is not None:
                return {'id':None,'ready':True,'status':'completed','dataset_id':existing['dataset_id'],
                        'message':'보관한 선수 기록을 확인했습니다.'}
            descriptor=self.catalog.describe(project,season)
            if descriptor['needs_connection']:raise ValueError(descriptor['message'])
            job_id=time.strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)
            private(self.outputs/job_id,directory=True)
            self.job={'id':job_id,'kind':'prepare_catalog','project':project,'season':season,
                      'status':'queued','started_at':utc_now(),'logs':[],'report':None,
                      'message':'선수 기록을 확인하고 있어요.'}
            self._persist()
            threading.Thread(target=self._catalog_worker,args=(job_id,project,season),daemon=True).start()
            return {'id':job_id,'status':'queued','ready':False}

    def _catalog_worker(self,job_id,project,season):
        def progress(message):
            with self.lock:
                if self.job['id']!=job_id or self.job['status']=='cancelling':raise PreparationCancelled()
                message=public_text(message)
                self.job.update(status='running',message=message)
                self.job['logs']=(self.job['logs']+[message])[-120:]
                self._persist()
        try:
            progress('보관한 기록과 공식 자료를 확인하고 있어요.')
            result=self.catalog.ensure(project,season,progress=progress)
            with self.lock:
                if self.job['status']=='cancelling':raise PreparationCancelled()
                self.job.update(status='completed',completed_at=utc_now(),dataset_id=result['dataset_id'],
                                message='선수 기록 준비가 끝났습니다. 바로 대결할 수 있어요.')
                self._persist()
        except PreparationCancelled:
            with self.lock:
                self.job.update(status='cancelled',completed_at=utc_now(),message='자료 준비를 중지했습니다. 확인된 보관 자료는 유지합니다.')
                self._persist()
        except Exception as exc:
            with self.lock:
                cancelled=self.job['status']=='cancelling'
                self.job.update(status='cancelled' if cancelled else 'failed',completed_at=utc_now(),
                                message='자료 준비를 중지했습니다. 확인된 보관 자료는 유지합니다.' if cancelled else public_text(exc))
                self._persist()

    def matchup_analyze(self,project,options):
        with self.lock:
            self._idle()
            from baseball_lab.matchup.service import analyze
            from baseball_lab.matchup.web import render
            from baseball_lab.data.lineage import checksum,content_hash
            analysis=analyze(self.root,project,options)
            sources=Path(__file__).parents[1]/'matchup'
            versions={p.name:checksum(p) for p in sorted(sources.glob('*.py'))}
            versions.update({'matchup.html':checksum(Path(__file__).with_name('matchup.html')),
                             'server.py':checksum(Path(__file__)),
                             'simulation/contracts.py':checksum(Path(__file__).parents[1]/'simulation/contracts.py'),
                             'data/catalog.py':checksum(Path(__file__).parents[1]/'data/catalog.py')})
            analysis['execution']={'engine_files':versions,'engine_id':content_hash(versions),'python':sys.version.split()[0]}
            job_id=time.strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)
            directory=self.outputs/job_id;private(directory,directory=True)
            analysis['execution']['execution_id']=job_id
            result=directory/'result';private(result,directory=True)
            report=f'/reports/{job_id}/result/report.html'
            write_json(result/'analysis.json',analysis)
            from baseball_lab.data.protection import open_private
            with open_private(result/'report.html') as file:file.write(render(project,analysis=analysis).encode('utf-8'))
            write_json(directory/'task.json',{'id':job_id,'kind':'matchup','project':project,'status':'completed',
                'started_at':analysis['created_at'],'completed_at':utc_now(),'report':report,'training_executed':False,
                'catalog_source':analysis['source']['id'],'message':f"{analysis['batter']['name']} ({analysis['batter']['season']}) vs {analysis['pitcher']['name']} ({analysis['pitcher']['season']}) · {analysis['simulation']['n']}타석"})
            return public_view({'analysis':analysis,'report':report})

    def upload(self, filename, content, source_url, acquired_at, usage_note):
        with self.lock:
            self._idle()
            if not filename.lower().endswith('.csv') or len(content)>32*1024*1024:
                raise ValueError('CSV 파일 한 개는 최대 32MB입니다.')
            from baseball_lab.data.statcast import manual_source, audit
            # The browser filename is informational only; never use it as a server path.
            directory=self.data/'uploads'/secrets.token_hex(8)
            private(directory,directory=True)
            path=directory/'official-export.csv';path.write_bytes(content);private(path)
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
            if kind not in ('fit','train','run','simulate'):raise ValueError('지원하지 않는 작업')
            if kind in ('run','simulate'):
                source='retrosheet' if kind=='simulate' else options.get('source','statcast')
                if source not in ('statcast','retrosheet'):raise ValueError('지원하지 않는 자료 연결입니다.')
                study=options.get('study','one_run')
                if study not in ('one_run','half_inning'):raise ValueError('학습 목표를 확인하세요.')
                if study=='half_inning' and source!='retrosheet':raise ValueError('이닝 득점 학습은 공식 경기 기록으로 실행합니다.')
                if source=='retrosheet':
                    first=date.fromisoformat(str(options.get('start','')));last=date.fromisoformat(str(options.get('end','')))
                    from baseball_lab.data.retrosheet_releases import RELEASES
                    if first.year not in RELEASES or last.year!=first.year or first>last:raise ValueError('2023·2024년 중 한 시즌의 날짜 범위를 선택하세요.')
                    start,end=str(first),str(last)
                else:
                    from baseball_lab.research.pipeline import Plan
                    plan=Plan(str(options.get('start','')),str(options.get('end','')))
                    start,end=plan.start,plan.end
                episodes=options.get('episodes',600);seed=options.get('seed',20261104)
                if type(episodes) is not int or not 20<=episodes<=100000:raise ValueError('학습 타석 수는 20~100,000 사이의 정수입니다.')
                if type(seed) is not int or not 0<=seed<=2**31-1:raise ValueError('재현 번호 범위를 확인하세요.')
                extra=['--mode','scoring' if source=='retrosheet' else 'run','--start',start,'--end',end,'--episodes',str(episodes),'--seed',str(seed)]
                if source=='retrosheet' and study=='half_inning':extra[1]='inning'
                if source=='retrosheet' and kind=='run':
                    if seed>2**31-3:raise ValueError('여러 재현 번호를 만들기 위해 seed는 2,147,483,645 이하여야 합니다.')
                    extra.extend(['--evaluation-n','500'])
                reference=options.get('authorization_reference','')
                if not isinstance(reference,str) or len(reference)>2000:raise ValueError('자료 연결 설정을 확인하세요.')
                if reference.strip():extra.extend(['--authorization-reference',reference.strip()])
                if kind=='simulate':
                    outs,bases=options.get('outs',0),options.get('bases',1)
                    observation=options.get('observation_source','model');style=options.get('policy_style','basic')
                    if type(outs) is not int or not 0<=outs<=2 or type(bases) is not int or not 0<=bases<=7:
                        raise ValueError('시작 아웃·주자 상태를 확인하세요.')
                    if observation not in ('model','observed') or style not in ('basic','random'):
                        raise ValueError('지원하는 관찰 방식을 선택하세요.')
                    extra=['--mode','simulate','--start',start,'--end',end,'--seed',str(seed),
                           '--outs',str(outs),'--bases',str(bases),'--observation-source',observation,'--policy-style',style]
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
            output=self.outputs/job_id;private(output,directory=True)
            self.job={'id':job_id,'kind':kind,'status':'queued','started_at':utc_now(),'logs':[],
                      'report':None,'message':'작업을 준비하고 있어요.'}
            if kind in ('run','simulate') and source=='retrosheet':self.job['source_year']=start[:4]
            if kind=='run':self.job['study']=study
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
                self.job.update(status='running',message='학습 없이 상황을 준비하고 있어요.' if self.job['kind']=='simulate' else '자료 준비부터 순서대로 진행하고 있어요.' if self.job['kind']=='run' else '기록을 검사하고 있어요.' if self.job['kind']=='fit' else '두 AI가 타석 대결을 학습하고 있어요.')
                self._persist()
            with (output/'output.log').open('w',encoding='utf-8') as log:
                private(output/'output.log')
                for line in process.stdout:
                    line=public_text(line)
                    log.write(line);log.flush()
                    with self.lock:
                        self.job['logs'].append(line.rstrip())
                        progress=re.search(r'학습 (\d+)/(\d+)(타석|상황)',line)
                        if line.startswith('단계 '):self.job['message']=line.strip()
                        if progress and self.job['kind'] in ('train','run'):
                            done,total=map(int,progress.groups()[:2]);unit=progress.group(3)
                            self.job.update(completed_episodes=done,target_episodes=total,message=line.strip()+' · 현재까지의 결과를 볼 수 있어요.')
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
                self.job.update(status=status,message=public_text(message),exit_code=code,completed_at=utc_now(),
                    report=f'/reports/{job_id}/result/report.html' if report.exists() else None)
                self._persist()
        except Exception as exc:
            if process and process.poll() is None:process.terminate();process.wait(timeout=10)
            with self.lock:
                self.job.update(status='failed',message=public_text(exc),completed_at=utc_now());self._persist()
        finally:
            with self.lock:
                if self.process is process:self.process=None

    def cancel(self):
        with self.lock:
            if not self.job or self.job['status'] not in ('queued','running'):raise ValueError('중지할 작업이 없습니다.')
            self.job.update(status='cancelling',message='중지하는 중입니다. 자료 수신 중이면 현재 확인을 마친 뒤 중지합니다.' if self.job.get('kind')=='prepare_catalog' else '중지하는 중입니다. 현재 작업 기록은 남겨 둡니다.');self._persist()
            if self.process and self.process.poll() is None:self.process.terminate()
            return {'message':'중지를 요청했습니다.'}


def make_handler(workbench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def handle(self):
            try:super().handle()
            except (BrokenPipeError,ConnectionResetError):
                # Navigation cancels an in-flight status poll; this is not a
                # failed training job. Keep actual request/worker errors visible.
                pass
        def _host_ok(self):
            host=self.headers.get('Host','')
            port=self.server.server_port
            return host in (f'127.0.0.1:{port}',f'localhost:{port}')
        def _json(self,payload,status=200):
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def _file(self,path):
            try:body=path.read_bytes()
            except OSError:return self._json({'error':'파일이 없어요.'},404)
            if path.name in ('summary.md','output.log'):
                body=public_text(body.decode('utf-8',errors='replace')).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def _html(self,body):
            data=body.encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if not self._host_ok():return self._json({'error':'로컬 주소로 접속하세요.'},403)
            path=urlparse(self.path).path
            pages={'/':'portal.html','/lab':'portal.html','/match':'match.html','/match/team':'workbench.html',
                   '/match/at-bat':'workbench.html','/simulation':'simulation.html','/lab/data':'data.html'}
            if path in ('/baseball','/eramatch'):
                from baseball_lab.matchup.web import render
                self._html(render('eramatch' if path=='/eramatch' else 'baseball',workbench.token))
            elif path in pages:
                body=Path(__file__).with_name(pages[path]).read_text(encoding='utf-8').replace('__SESSION_TOKEN__',workbench.token)
                self._html(body)
            elif path=='/api/state':
                try:self._json(workbench.state(parse_qs(urlparse(self.path).query).get('project',[None])[0]))
                except ValueError as exc:self._json({'error':str(exc)},400)
            elif path=='/api/storage':self._json(workbench.storage.inventory())
            elif path=='/api/catalog':
                try:self._json(public_view({'schema':'dataset-index-v1','sources':workbench.catalog.list_sources()}))
                except (ValueError,KeyError,TypeError,OSError) as exc:self._json({'error':public_text(exc)},400)
            elif path=='/api/knowledge':
                try:
                    from baseball_lab.data.knowledge import get_knowledge
                    key=parse_qs(urlparse(self.path).query).get('metric',[None])[0]
                    self._json(get_knowledge(key))
                except (ValueError,KeyError,TypeError) as exc:self._json({'error':public_text(exc)},400)
            elif path=='/api/matchup/catalog':
                try:
                    from baseball_lab.matchup.service import overview
                    query=parse_qs(urlparse(self.path).query)
                    result=overview(workbench.root,query.get('project',['baseball'])[0],
                        role=query.get('role',[None])[0],query=query.get('query',[''])[0],season=query.get('season',[None])[0])
                    self._json(public_view(result))
                except (ValueError,KeyError,TypeError,OSError) as exc:self._json({'error':public_text(exc)},400)
            elif path.startswith('/reports/'):
                from urllib.parse import unquote
                resolved=(workbench.outputs/unquote(path[len('/reports/'):])).resolve()
                if not resolved.is_relative_to(workbench.outputs.resolve()) or resolved.name not in ('report.html','summary.md','output.log'):
                    return self._json({'error':'허용하지 않는 경로'},403)
                if resolved.name=='report.html' and (resolved.parent/'analysis.json').is_file():
                    try:
                        from baseball_lab.matchup.web import render
                        data=json.loads((resolved.parent/'analysis.json').read_text(encoding='utf-8'))
                        return self._html(render(data['project'],token=workbench.token,analysis=data))
                    except (OSError,ValueError,KeyError,TypeError) as exc:return self._json({'error':public_text(exc)},409)
                if resolved.name=='report.html' and (resolved.parent/'research.json').is_file():
                    try:
                        evidence=json.loads((resolved.parent/'research.json').read_text(encoding='utf-8'))
                        if evidence.get('schema')=='E01-R1-research-v1':
                            external=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(resolved.parent.glob('external-*.json'))]
                            evidence['external_evaluation']=[r for r in external if r.get('run_id')==evidence['run_id']]
                            from baseball_lab.experiments.match.reporting.report import render
                            return self._html(render(evidence))
                        if evidence.get('schema')=='Match-half-inning-research-v1':
                            from baseball_lab.experiments.match.reporting.inning import render
                            return self._html(render(evidence))
                    except (OSError,ValueError,KeyError,TypeError) as exc:
                        return self._json({'error':public_text(f'결과 근거를 읽을 수 없습니다: {exc}')},409)
                if resolved.name=='report.html' and (resolved.parent/'session.json').is_file():
                    try:
                        from baseball_lab.simulation.scoring import render
                        return self._html(render(json.loads((resolved.parent/'session.json').read_text(encoding='utf-8'))))
                    except (OSError,ValueError,KeyError,TypeError) as exc:return self._json({'error':public_text(exc)},409)
                if resolved.name=='report.html':
                    try:return self._html(public_text(resolved.read_text(encoding='utf-8')))
                    except OSError:return self._json({'error':'결과 파일이 없습니다.'},404)
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
                if path=='/api/matchup/prepare':
                    payload=json.loads(body)
                    if not isinstance(payload,dict):raise ValueError('선수 기록 준비 설정을 확인하세요.')
                    result=workbench.matchup_prepare(project=payload.get('project','baseball'),season=payload.get('season',2024))
                elif path=='/api/matchup/import':result=workbench.matchup_prepare(body)
                elif path=='/api/matchup/analyze':
                    payload=json.loads(body)
                    if not isinstance(payload,dict):raise ValueError('대결 설정이 필요합니다.')
                    result=workbench.matchup_analyze(payload.get('project'),payload.get('options'))
                elif path=='/api/upload':
                    from urllib.parse import unquote
                    result=workbench.upload(unquote(self.headers.get('X-Filename','export.csv')),body,
                        unquote(self.headers.get('X-Source-URL','')),unquote(self.headers.get('X-Acquired-At','')),
                        unquote(self.headers.get('X-Usage-Note','')))
                elif path=='/api/start':
                    payload=json.loads(body)
                    if not isinstance(payload,dict):raise ValueError('올바른 작업 요청이 아닙니다.')
                    result=workbench.start(payload['kind'],payload.get('options',{}))
                elif path=='/api/cancel':result=workbench.cancel()
                elif path in ('/api/storage/preview','/api/storage/delete','/api/storage/verify'):
                    payload=json.loads(body)
                    if not isinstance(payload,dict):raise ValueError('올바른 자료 관리 요청이 아닙니다.')
                    with workbench.lock:
                        workbench._idle()
                        if path.endswith('/preview'):result=workbench.storage.preview(payload['id'])
                        elif path.endswith('/verify'):result=workbench.storage.verify(payload['id'])
                        else:result=workbench.storage.delete(payload['confirmation'],payload.get('confirmed'))
                else:return self._json({'error':'지원하지 않는 요청'},404)
                self._json(result)
            except (ValueError,KeyError,TypeError,OSError,csv.Error) as exc:self._json({'error':public_text(exc)},400)
    return Handler


def serve(root,port=8765,open_browser=False):
    workbench=Workbench(root)
    server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(workbench))
    server.daemon_threads=True
    address=f'http://127.0.0.1:{server.server_port}'
    print('야구 AI 연구실을 열었습니다: '+address,flush=True)
    print('BaseballLab 통계 대결 · Match AI 학습 · EraMatch 시대 대결을 선택하세요. 종료: Ctrl+C',flush=True)
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
