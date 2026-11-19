"""Fixed public pitch CSV releases. Source licensing and upstream rights differ."""
import hashlib
import json
import secrets
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path,PurePosixPath
from urllib.parse import urlparse
from zipfile import ZipFile
from .lineage import checksum,write_json,utc_now
from .protection import private,open_private
from .warehouse import local_path

SOURCES={
    'MLB':{'repository':'pschale/mlb-pitch-data-20152018','revision':'2',
           'url':'https://www.kaggle.com/datasets/pschale/mlb-pitch-data-20152018',
           'license':'Data files © Original Authors; publisher says scraped MLB Gameday',
           'credit':'Public distribution by Peter Schale; original MLB Gameday records'},
    'KBO':{'repository':'NextPitchh/KBO_Crawler','revision':'18a5810d188c81f989499844ef525dbb594a29d1',
           'url':'https://github.com/NextPitchh/KBO_Crawler',
           'license':'Public repository; no explicit dataset license; upstream Naver rights unverified',
           'credit':'NextPitchh K-Moneyball public pitch CSV release, Naver Sports derived'},
    'NPB':{'repository':'armstjc/Nippon-Baseball-Data-Repository','revision':'5f9108abdaf7db69d3ca976381cf5f59716e75e8',
           'url':'https://github.com/armstjc/Nippon-Baseball-Data-Repository',
           'license':'Publisher custom MIT with attribution; upstream SPAIA rights unverified',
           'credit':'This uses data sourced from the Nippon Baseball Data Repository, which can be accessed here: https://github.com/armstjc/Nippon-Baseball-Data-Repository'}}
HOSTS={'api.github.com','raw.githubusercontent.com','codeload.github.com','www.kaggle.com','storage.googleapis.com'}


def safe(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.port not in (None,443):
        raise ValueError('등록된 공개 배포 호스트만 읽습니다.')


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download(url,path,limit):
    safe(url);path=Path(path)
    if path.exists() or path.is_symlink():raise FileExistsError('기존 배포 원본을 덮어쓰지 않습니다.')
    for attempt in range(3):
        part=path.with_suffix(path.suffix+'.part')
        try:
            with urllib.request.build_opener(Redirect()).open(urllib.request.Request(url,headers={'User-Agent':'BaseballLab public dataset research'}),timeout=45) as response,open_private(part) as out:
                size=0
                while chunk:=response.read(1024*1024):
                    size+=len(chunk)
                    if size>limit:raise ValueError('배포 원본 크기 한도 초과')
                    out.write(chunk)
                expected=response.headers.get('Content-Length')
                if expected is not None and size!=int(expected):raise ConnectionError('배포 수신 중단')
            part.replace(path);return
        except (TimeoutError,ConnectionError):
            if attempt==2:raise
            time.sleep(2**attempt)
        finally:part.unlink(missing_ok=True)


def json_download(url,path):
    download(url,path,8*1024*1024)
    return json.loads(path.read_text(encoding='utf-8'))


def member_path(root,folder,name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name:raise ValueError('배포 파일 경로 이탈')
    path=local_path(root,folder/'raw'/str(p));private(path.parent,directory=True)
    return path


def collect(root,league):
    root=Path(root).resolve();spec=SOURCES[league]
    base=local_path(root,root/'data/local/pitch-sources');private(base,directory=True)
    for file in sorted(base.glob(f'{league.lower()}-*/manifest.json'),reverse=True):
        m=json.loads(file.read_text(encoding='utf-8'))
        if m.get('revision')!=spec['revision'] or m.get('status')!='ACQUIRED':continue
        for f in m['files']:
            if checksum(local_path(root,root/f['path']))!=f['sha256']:raise ValueError('기존 투구 원본 해시 불일치')
        return file
    folder=base/f'{league.lower()}-{spec["revision"][:8]}-{secrets.token_hex(4)}';private(folder,directory=True)
    manifest={'schema':'pitch-source-release-v1','league':league,**spec,'created_at':utc_now(),
              'status':'ACQUIRING','files':[],'rights_status':'PUBLISHER_DISTRIBUTION_UPSTREAM_UNVERIFIED',
              'raw_redistribution':False,'training_eligibility':'field and temporal checks required; acquisition alone is not validation'}
    target=folder/'manifest.json';write_json(target,manifest)
    if league=='MLB':
        meta=json_download('https://www.kaggle.com/api/v1/datasets/view/'+spec['repository'],folder/'metadata.json')
        files=json_download('https://www.kaggle.com/api/v1/datasets/list/'+spec['repository']+'?datasetVersionNumber=2',folder/'files.json')
        if meta['currentVersionNumber']!=2:raise ValueError('검토한 MLB 배포 버전과 다릅니다.')
        expected={r['name']:int(r['totalBytes']) for r in files['datasetFiles']}
        archive=folder/'source.zip'
        download('https://www.kaggle.com/api/v1/datasets/download/'+spec['repository']+'?datasetVersionNumber=2',archive,512*1024*1024)
        with ZipFile(archive) as z:
            if len(z.infolist())>20:raise ValueError('배포 멤버 수 한도')
            for info in z.infolist():
                if info.is_dir():continue
                if info.filename not in expected or info.file_size!=expected[info.filename] or info.file_size>1200*1024*1024:raise ValueError('공개 파일 목록과 ZIP 내용 불일치')
                path=member_path(root,folder,info.filename)
                with z.open(info) as src,open_private(path) as out:
                    while chunk:=src.read(1024*1024):out.write(chunk)
                manifest['files'].append({'path':str(path.relative_to(root)),'source_path':info.filename,'sha256':checksum(path),'bytes':path.stat().st_size})
        manifest['archive_sha256']=checksum(archive)
    else:
        repo=spec['repository'];revision=spec['revision']
        tree=json_download(f'https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1',folder/'tree.json')
        if tree.get('truncated'):raise ValueError('원천 파일 트리가 잘렸습니다.')
        prefix='data/pbp_full/' if league=='KBO' else 'pbp/'
        entries=[r for r in tree['tree'] if r['type']=='blob' and r['path'].startswith(prefix) and r['path'].endswith('.csv')]
        if not entries:raise ValueError('공개 투구 CSV 없음')
        def acquire(entry):
            name=entry['path'];path=member_path(root,folder,name)
            # Already acquired NPB files are verified and copied, never rewritten.
            prior=next((root/f['path'] for m in (root/'data/local/community/npb-armstjc').glob('*/manifest.json') for f in json.loads(m.read_text(encoding='utf-8')).get('files',[]) if f.get('url')==f'https://raw.githubusercontent.com/{repo}/{revision}/{name}' and (root/f['path']).is_file()),None) if league=='NPB' else None
            if prior:
                with prior.open('rb') as src,open_private(path) as out:
                    while chunk:=src.read(1024*1024):out.write(chunk)
            else:download(f'https://raw.githubusercontent.com/{repo}/{revision}/{name}',path,256*1024*1024)
            size=path.stat().st_size
            blob=hashlib.sha1(f'blob {size}\0'.encode())
            with path.open('rb') as f:
                while chunk:=f.read(1024*1024):blob.update(chunk)
            if size!=entry['size'] or blob.hexdigest()!=entry['sha']:raise ValueError('고정 Git 배포 파일과 원본이 다릅니다.')
            print(f'{league} 수집 · {name}',flush=True)
            return {'path':str(path.relative_to(root)),'source_path':name,'sha256':checksum(path),'git_blob_sha':entry['sha'],'bytes':size}
        if league=='KBO':
            # One immutable repository archive replaces thousands of HTTP calls.
            archive=folder/'source.zip';download(f'https://codeload.github.com/{repo}/zip/{revision}',archive,512*1024*1024)
            with ZipFile(archive) as z:
                for entry in entries:
                    path=member_path(root,folder,entry['path']);name=f'{repo.split("/")[1]}-{revision}/'+entry['path']
                    info=z.getinfo(name)
                    if info.file_size!=entry['size']:raise ValueError('고정 KBO 파일 크기 불일치')
                    body=z.read(info)
                    if hashlib.sha1(f'blob {len(body)}\0'.encode()+body).hexdigest()!=entry['sha']:raise ValueError('KBO Git blob 불일치')
                    with open_private(path) as out:out.write(body)
                    manifest['files'].append({'path':str(path.relative_to(root)),'source_path':entry['path'],'sha256':checksum(path),'git_blob_sha':entry['sha'],'bytes':len(body)})
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:manifest['files']=list(pool.map(acquire,entries))
    manifest.update(status='ACQUIRED',csv_files=len(manifest['files']),bytes=sum(f['bytes'] for f in manifest['files']))
    write_json(target,manifest);print(f'{league} 원본 확인 완료 · {len(manifest["files"])} CSV',flush=True)
    return target
