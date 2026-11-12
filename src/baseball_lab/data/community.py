"""Versioned community CSV acquisition; publisher license != upstream audit."""
import csv
import io
import json
import re
import secrets
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile
from collections import Counter
from .lineage import checksum,write_json,utc_now
from .protection import private,open_private
from .warehouse import local_path

KBO_SOURCES=(
    'netsong/kbo-player-stats-19822025',
    'mattop/korean-baseball-pitching-data-1982-2021',
    'mattop/baseball-kbo-batting-data-1982-2021',
    'lazyjun01/kbo-defensive-data2001-2024',
    'lazyjun01/kbo-runners-data2001-2024')
HOSTS={'www.kaggle.com','kaggle.com','storage.googleapis.com'}


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def safe_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.port not in (None,443):raise ValueError('등록된 공개 배포 호스트만 허용합니다.')


def download(url,target,limit):
    safe_url(url);target=Path(target)
    if target.exists() or target.is_symlink():raise ValueError('기존 원본을 덮어쓰지 않습니다.')
    with urllib.request.build_opener(Redirect()).open(url,timeout=45) as response,open_private(target) as f:
        expected=response.headers.get('Content-Length');size=0
        while chunk:=response.read(1024*1024):
            size+=len(chunk)
            if size>limit:raise ValueError('공개 자료 크기 한도 초과')
            f.write(chunk)
        if expected is not None and size!=int(expected):raise ValueError('배포 파일이 중간에 끊겼습니다.')


def integer(value):
    if value is None or str(value).strip() in ('','-','NA','NaN','nan'):return None
    text=str(value).replace(',','').strip()
    if not re.fullmatch(r'\d+(?:\.0+)?',text):raise ValueError('정수 계수로 확인할 수 없습니다: '+text)
    return int(text.split('.')[0])


def outs(value):
    if value in (None,'','-'):return None
    if re.fullmatch(r'[12]/3',str(value).strip()):return int(str(value).strip()[0])
    m=re.fullmatch(r'(\d+)(?:\s+([12])/3|\.([012]))?',str(value).strip())
    if not m:raise ValueError('원문 이닝의 분수 표기를 확인하세요: '+str(value))
    return int(m[1])*3+int(m[2] or m[3] or 0)


def extract(archive,folder):
    files=[];total=0
    with ZipFile(archive) as z:
        if len(z.infolist())>30:raise ValueError('배포 파일 개수 한도 초과')
        for item in z.infolist():
            if item.is_dir():continue
            p=Path(item.filename)
            if p.name!=item.filename or '\\' in item.filename or p.suffix.lower()!='.csv':raise ValueError('배포본에 허용하지 않은 CSV 경로가 있습니다.')
            total+=item.file_size
            if total>64*1024*1024 or item.file_size>32*1024*1024:raise ValueError('압축 해제 크기 한도 초과')
            path=folder/p.name
            with z.open(item) as src,open_private(path) as out:
                while chunk:=src.read(1024*1024):out.write(chunk)
            files.append(path)
    return files


def register(root,rows,meta):
    folder=local_path(root,Path(root).resolve()/'data/local/collections'/('community-'+secrets.token_hex(8)))
    private(folder,directory=True);target=folder/'rows.jsonl'
    with open_private(target) as out:
        for row in rows:out.write((json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n').encode())
    manifest={'schema':'league-source-snapshot-v1','status':'ACQUIRED_PARSED','acquired_at':utc_now(),
        'rows_file':'rows.jsonl','rows_sha256':checksum(target),'row_count':len(rows),'source_status':'REAL_OBSERVED',
        'rights_status':'PUBLISHER_DECLARED_UPSTREAM_UNVERIFIED','training_registered':False,**meta}
    write_json(folder/'manifest.json',manifest)
    return manifest


def player_rows(path):
    role='pitcher' if 'pitching' in path.name else 'batter';digest=checksum(path)
    with path.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    seen=set();result=[]
    fields=('G','PA','AB','R','H','2B','3B','HR','TB','RBI','SB','CS','BB','HBP','SO','GDP','SF','SH','TBF','ER','CG','SHO','W','L','SV','HLD')
    for raw in rows:
        year=integer(raw['Season']);pid=raw['Id'];key=(pid,year)
        if key in seen:raise ValueError('제공자가 시즌 합계라고 밝힌 선수 행이 중복됐습니다.')
        seen.add(key)
        counts={k:integer(raw[k]) for k in fields if k in raw}
        if 'IP' in raw:counts['IP_OUTS']=outs(raw['IP'])
        result.append({'league':'KBO','season':year,'role':role,'granularity':'player_season',
            'source_namespace':'kaggle-netsong-kbo','source_player_id':pid,'source_sha256':digest,'counts':counts,
            'source_fields':{'Name':raw['Player'],'team_label':raw['Team']},'row_kind':'season_total'})
    return result


def acquire_kbo(root,ref):
    if ref not in KBO_SOURCES:raise ValueError('확인한 CSV 배포만 수집합니다.')
    root=Path(root).resolve();base=local_path(root,root/'data/local/community'/('kaggle-'+ref.replace('/','-')+'-'+secrets.token_hex(6)))
    private(base,directory=True);metadata=base/'metadata.json'
    source='https://www.kaggle.com/api/v1/datasets/view/'+ref;download(source,metadata,4*1024*1024)
    m=json.loads(metadata.read_text());version=m['currentVersionNumber'];license=m.get('licenseName')
    if not license or license=='Unknown':raise ValueError('게시자의 데이터 라이선스 선언이 없습니다.')
    for previous in (root/'data/local/community').glob('kaggle-'+ref.replace('/','-')+'-*/manifest.json'):
        local_path(root,previous);cached=json.loads(previous.read_text())
        if cached.get('version')!=version:continue
        if checksum(local_path(root,previous.parent/'source.zip'))!=cached['archive_sha256']:raise ValueError('보관한 공개 배포 ZIP이 변경됐습니다.')
        for item in cached['files']:
            if checksum(local_path(root,root/item['path']))!=item['sha256']:raise ValueError('보관한 CSV가 변경됐습니다.')
        return cached
    archive=base/'source.zip';url='https://www.kaggle.com/api/v1/datasets/download/'+ref+'?datasetVersionNumber='+str(version)
    download(url,archive,32*1024*1024);files=extract(archive,base);summaries=[];all_rows=[]
    for path in files:
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);columns=reader.fieldnames;raw=list(reader)
        year_key='Season' if 'Season' in columns else 'year';years=sorted({integer(r[year_key]) for r in raw})
        issues=0
        if 'steals' in columns:issues=sum(integer(r['steals'])+integer(r['caught_stealing'])!=integer(r['steal_attempts']) for r in raw)
        summaries.append({'path':str(path.relative_to(root)),'sha256':checksum(path),'rows':len(raw),'seasons':years,'fields':columns,
            'quality_issues':{'steal_attempts_not_equal_sb_plus_cs':issues} if 'steals' in columns else {}})
        if ref.startswith('netsong/'):all_rows.extend(player_rows(path))
    manifest={'schema':'community-raw-acquisition-v1','league':'KBO','source_namespace':'kaggle-'+ref,
        'source_url':'https://www.kaggle.com/datasets/'+ref,'download_url':url,'version':version,'created_at':utc_now(),
        'source_status':'REAL_OBSERVED','rights_status':'PUBLISHER_DECLARED_UPSTREAM_UNVERIFIED','publisher_license':license,
        'metadata_sha256':checksum(metadata),'archive_sha256':checksum(archive),'files':summaries,
        'raw_rows':sum(x['rows'] for x in summaries),'training_ready':False,
        'limitations':['Publisher license and accuracy claims are recorded, not independently certified upstream rights or validation.',
            'Auxiliary running/fielding tables remain separate; inconsistent fields are not repaired or used as transitions.']}
    if all_rows:
        registered=register(root,all_rows,{'league':'KBO','source_namespace':'kaggle-netsong-kbo','source_url':manifest['source_url'],
            'publisher_license':license,'source_version':version,'raw_manifest':str((base/'manifest.json').relative_to(root))})
        manifest['registered_rows']=registered['row_count']
    write_json(base/'manifest.json',manifest)
    return manifest
