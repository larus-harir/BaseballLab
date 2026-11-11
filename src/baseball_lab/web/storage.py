"""Fixed local collections, read-only inventory and explicit two-step removal."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time
from baseball_lab.data.retrosheet_releases import RELEASES
from baseball_lab.data.protection import private

CATEGORIES={'official':'공식 공개 원본','private':'사용자 제공 비공개 자료','derived':'정제·모델 중간 자료',
            'weights':'학습 모델·저장 시점','reports':'결과·로그','test':'테스트 전용','other':'기타 보관 자료'}


def scan(path):
    path=Path(path);files=[];links=[];counts={k:0 for k in CATEGORIES}
    for directory,dirs,names in os.walk(path,followlinks=False):
        for name in list(dirs):
            if (Path(directory)/name).is_symlink():links.append(name);dirs.remove(name)
        for name in names:
            p=Path(directory)/name
            if p.is_symlink():links.append(name);continue
            stat=p.stat();relative=str(p.relative_to(path));files.append((relative,stat.st_size,stat.st_mtime_ns))
            category=('test' if 'MOCK_TEST_ONLY' in name else 'weights' if 'checkpoints' in p.parts or 'policy_versions' in p.parts else
                      'official' if name.endswith(('.zip','.csv')) and 'statcast' not in p.parts else
                      'private' if name.endswith('.csv') else 'derived' if name in ('dataset.json','model.json','models.json','quality.json') else
                      'reports' if name.endswith(('.html','.md','.log','.json')) else 'other')
            counts[category]+=stat.st_size
    return {'bytes':sum(f[1] for f in files),'file_count':len(files),'categories':counts,'links':links,
            'changed_at':max((f[2] for f in files),default=0)/1e9,
            'fingerprint':hashlib.sha256(json.dumps(sorted(files)).encode()).hexdigest()}


class Storage:
    def __init__(self,root):self.root=Path(root).resolve();self.pending={};self.verifications={}

    def _targets(self):
        targets={}
        for year in RELEASES:
            p=self.root/f'data/local/retrosheet/official-{year}'
            if p.exists():targets[f'source:{year}']=(p,f'{year}년 MLB 경기 기록','official')
        p=self.root/'data/local/statcast'
        if p.exists():targets['private:statcast']=(p,'사용자가 연결한 투구 자료','private')
        from baseball_lab.data.catalog import DatasetCatalog
        catalog_targets=[(f'mlb-{year}',f'BaseballLab · MLB {year} 선수 기록','official')
                         for year in DatasetCatalog(self.root).supported_seasons('baseball')]
        catalog_targets.append(('kbo-assignment','EraMatch · 사용자 과제 원본과 선수 기록','private'))
        for source,label,category in catalog_targets:
            p=self.root/'data/local/catalog'/source
            if p.exists():targets['catalog:'+source]=(p,label,category)
        output=self.root/'outputs/workbench'
        try:self._safe(output);safe_output=True
        except ValueError:safe_output=False
        if safe_output and output.exists():
            for p in sorted(output.iterdir(),reverse=True):
                if p.is_dir() and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p.name):
                    targets['run:'+p.name]=(p,'실행 '+p.name,'reports')
        return targets

    def _safe(self,path):
        relative=path.relative_to(self.root);current=self.root
        for part in relative.parts:
            current=current/part
            if current.is_symlink():raise ValueError('심볼릭 링크가 포함된 저장 경로는 관리 작업을 허용하지 않습니다.')
        if not path.resolve().is_relative_to(self.root):raise ValueError('저장 경로 이탈')
        return path

    def inventory(self):
        targets=self._targets();items=[]
        run_sources={}
        catalog_runs={}
        for identifier,(p,_,_) in targets.items():
            if not identifier.startswith('run:') or p.is_symlink():continue
            try:
                self._safe(p);r=p/'result/research.json'
                task=p/'task.json'
                if task.is_file() and not task.is_symlink():
                    metadata=json.loads(task.read_text(encoding='utf-8'))
                    if metadata.get('source_year'):run_sources[identifier]={str(metadata['source_year'])}
                    if metadata.get('catalog_source'):catalog_runs[identifier]=metadata['catalog_source']
                if r.is_file() and not r.is_symlink():
                    data=json.loads(r.read_text(encoding='utf-8'));run_sources[identifier]={d[:4] for d in data.get('model',{}).get('selected_dates',[])}
                    run_sources[identifier].update(f.stem.split('-')[-1] for f in (p/'result').glob('external-*.json'))
            except (OSError,ValueError,TypeError):continue
        for identifier,(p,label,category) in targets.items():
            try:
                self._safe(p);stats=scan(p)
                dependencies=[key for key,years in run_sources.items() if identifier.startswith('source:') and identifier.split(':')[1] in years]
                dependencies.extend(key for key,source in catalog_runs.items() if identifier=='catalog:'+source)
                # KBO assignment ZIP/CSV are private user materials, never "official".
                if identifier=='catalog:kbo-assignment':
                    stats['categories']['private']+=stats['categories']['official'];stats['categories']['official']=0
                items.append({'id':identifier,'label':label,'category':category,'location':str(p.relative_to(self.root)),
                              **{k:stats[k] for k in ('bytes','file_count','changed_at','categories')},
                              'dependent_runs':len(dependencies),'verified':self.verifications.get(identifier,{}).get('message','해시 검사 전입니다') if self.verifications.get(identifier,{}).get('fingerprint')==stats['fingerprint'] else '해시 재검사 전입니다',
                              'deletable':not stats['links'],'link_warning':bool(stats['links']),
                              'use':'선수별 사건 비율·확률 대결' if identifier.startswith('catalog:') else '아웃·주자·득점 상황' if category=='official' else '별도 투구 연구' if category=='private' else '학습·관찰의 실행 기록'})
            except (OSError,ValueError):
                items.append({'id':identifier,'label':label,'category':category,'bytes':None,'deletable':False,'link_warning':True})
        for location,label in (('data/local/retrosheet','이전 조사 자료·도구'),('outputs/E01','명령줄에서 만든 연구 결과')):
            p=self.root/location
            try:
                self._safe(p)
                if not p.is_dir():continue
                stats=scan(p)
                used=sum(i.get('bytes') or 0 for i in items if i.get('location','').startswith(location+'/'))
                remaining=stats['bytes']-used
                if remaining>0:items.append({'id':'other:'+location,'label':label,'category':'other','location':location,
                    'bytes':remaining,'file_count':stats['file_count'],'deletable':False,'dependent_runs':0,
                    'use':'기존 자료는 자동으로 지우지 않습니다. 개별 검토가 필요한 보관 영역입니다.'})
            except (OSError,ValueError):continue
        synced=any(x.lower() in str(self.root).lower() for x in ('onedrive','dropbox','icloud','google drive'))
        return {'items':items,'categories':CATEGORIES,'platform':os.name,'local_only':True,'encrypted_by_app':False,
                'permissions':'POSIX의 새 자료는 폴더 700·파일 600' if os.name=='posix' else 'Windows 사용자별 ACL은 앱에서 검증하지 않았습니다.',
                'sync_warning':synced,'retention':'자동 삭제하지 않습니다. 사용자가 확인한 항목만 삭제합니다.',
                'transmission':'자료 준비 때 공식 제공자와 통신합니다. 사용자 CSV·학습 가중치를 외부로 업로드하는 기능은 없습니다.'}

    def preview(self,identifier):
        target=self._targets().get(identifier)
        if not target:raise ValueError('지정된 보관 항목이 없습니다.')
        path=self._safe(target[0]);stats=scan(path)
        if stats['links']:raise ValueError('링크가 포함된 폴더는 삭제할 수 없습니다.')
        token=secrets.token_urlsafe(24);self.pending[token]=(identifier,stats['fingerprint'],time.monotonic()+120)
        item=next(i for i in self.inventory()['items'] if i['id']==identifier)
        return {'confirmation':token,'item':item,'warning':'삭제하면 관련 연구를 재현하거나 이어서 확인하지 못할 수 있습니다. 원본은 동일 배포가 유지될 때만 다시 받을 수 있습니다. 휴지통 복구 기능은 없습니다.'}

    def verify(self,identifier):
        target=self._targets().get(identifier)
        if not target or not identifier.startswith(('source:','catalog:')):raise ValueError('등록된 원본 기록을 선택하세요.')
        path=self._safe(target[0])
        if scan(path)['links']:raise ValueError('링크가 포함된 자료는 검사하지 않습니다.')
        if identifier.startswith('catalog:'):
            from baseball_lab.matchup.catalog import read_catalog
            catalog=read_catalog(self.root,identifier.split(':',1)[1])
            message='선수 자료·원본 파일 해시 일치. 자료의 공인 정확도·인과 타당성·재배포 권한의 인증은 아닙니다.'
            if not catalog:raise ValueError('선수 카탈로그가 없습니다.')
            self.verifications[identifier]={'fingerprint':scan(path)['fingerprint'],'message':message}
            return {'id':identifier,'verified':True,'message':message}
        from baseball_lab.r1.data import load
        from baseball_lab.data.lineage import checksum
        year=int(identifier.split(':')[1])
        if checksum(path/f'{year}plays.zip')!=RELEASES[year]['sha256']:raise ValueError('공식 배포 해시와 일치하지 않습니다.')
        data=load(path/'dataset.json')
        message=f"원본·정제 기록 해시 일치 · {data['manifest']['games']:,}경기. 인과 타당성이나 암호화의 인증은 아닙니다."
        self.verifications[identifier]={'fingerprint':scan(path)['fingerprint'],'message':message}
        return {'id':identifier,'verified':True,'message':message}

    def delete(self,confirmation,confirmed):
        if confirmed is not True:raise ValueError('사용자의 명시적 삭제 확인이 필요합니다.')
        request=self.pending.pop(confirmation,None)
        if not request or request[2]<time.monotonic():raise ValueError('삭제 확인이 만료됐습니다. 다시 확인하세요.')
        identifier,fingerprint,_=request;target=self._targets().get(identifier)
        if not target:raise ValueError('대상 항목이 변경됐습니다.')
        path=self._safe(target[0]);current=scan(path)
        if current['links'] or current['fingerprint']!=fingerprint:raise ValueError('자료가 변경돼 삭제하지 않았습니다. 다시 확인하세요.')
        shutil.rmtree(path)
        return {'deleted':identifier,'message':'확인한 보관 항목만 삭제했습니다.'}
