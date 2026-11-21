"""Versioned public tracking releases; never downloads from restricted originals."""
from pathlib import Path
from urllib.parse import urlparse,urlencode
from zipfile import ZipFile
import csv,hashlib,json,secrets,urllib.request
from .pitch_sources import download
from .lineage import checksum,write_json,utc_now
from .protection import private,open_private
from .warehouse import local_path

NPB_RENDERER='https://gs-files.spaia.jp/js/npb/pc/pc.one-ball.v0.3.5.bundle.js'
NPB_RENDERER_SHA='3daed77f207e3c53aa45bb56a78d58d9350152445914a7f9de48fbd662301e79'
KBO_SHA={
 '03':'59636cf415e954804557db176337b556b43df929db649c567853794e1f6c9f65',
 '04':'26e5bb69532bfc672b21e60f229925be5f602a9e2bc8bed942ad7c752d060b11',
 '05':'ce6b8b96aca0533e1721990772cf72008ff5824f2f61a7421a4a51b76d4554c5',
 '06':'ce1f1de98b67ce24042d06f660b444ef671c1bd57e2de2fb70f0ca73f91f9f2f',
 '07':'37b68596eadf40e65d7447cd81416b94424986ff88704e2520fe39e20e46577c',
 '08':'952254b4ac7cfe9f7f516c7f5e424c4297268b58a0f5c16ac8cfbc48acb19643',
 '09':'fca3e2bf0c665c1e99d0fa0f2c8c93c05bcd7b72c7f2d19b6cbdf3024e87a297',
 '10':'3e0de2eb40a282d797ba900100fab2a07697dd6477a0f1d193389e6c1589bf6e'}


def definitions(root):
    folder=local_path(Path(root),Path(root)/'data/local/tracking-definitions');private(folder,directory=True)
    path=folder/'npb-renderer.js'
    if not path.exists():download(NPB_RENDERER,path,2*1024*1024,hosts={'gs-files.spaia.jp'})
    if checksum(path)!=NPB_RENDERER_SHA:raise ValueError('NPB 구종·화면 정의가 검토한 버전과 다릅니다.')
    return path


def validate_kbo(files):
    for f in files:
        if f['sha256']!=KBO_SHA[f['name'][-6:-4]]:raise ValueError('KBO 공개 CSV가 검토한 배포본과 다릅니다.')

KBO_FILES={
 'kbo_LOTTE_2026-03.csv':'1PW-m0o9rtNcW1IdGmFDPz5JiioMSwJIl',
 'kbo_LOTTE_2026-04.csv':'1hc4VJhpl09cBh5p1ZzC2xeDpCvsTmG3o',
 'kbo_LOTTE_2026-05.csv':'10Kw_J7K8OnoTtKBk01n7ldaRmjnfGM-C',
 'kbo_LOTTE_2026-06.csv':'1NCUZLoSE5g8F7cDO45AE95Dv_85u-McE',
 'kbo_LOTTE_2026-07.csv':'1wG7K3sqBRR1W6TcE3ptO9jDhjx1q3HDm',
 'kbo_LOTTE_2026-08.csv':'1FBvxlAVEM1VBnNRntHfLwLdOD0DDDpe9',
 'kbo_LOTTE_2026-09.csv':'1I4tLgy8MX0scNfZrC0e_Ano_gMKeo27m',
 'kbo_LOTTE_2026-10.csv':'1tTf7VXkZm6ng7S2WjE1SjkL9ygs_23ic'}
RELEASES={
 'mlb-statcast-2017-2021':{'league':'MLB','repository':'s903124/mlb-statcast-data','version':4,'limit':600*1024*1024},
 'mlb-tracking-2024-2026':{'league':'MLB','repository':'yasunorim/mlb-statcast-bat-tracking-2024-2025','version':2,'limit':450*1024*1024},
 'kbo-locations-2026':{'league':'KBO','repository':'ekim56korea/kbo-pitch-data','revision':'c795fdb67ac19b8f347cdb623e4a523e5761909e',
   'folder':'16rUpoxQJph1zW2c6wxgfEUYkqycftpDE','credit':'ekim56korea public KBO 2026 Lotte-participant games; original Naver relay',
   'scope':'144 Lotte-participant regular games, both teams; not the full league season'}}


def collect(root,name):
    root=Path(root).resolve();spec=RELEASES[name];base=local_path(root,root/'data/local/tracking-releases');private(base,directory=True)
    for p in sorted(base.glob(name+'-*/manifest.json')):
        m=json.loads(p.read_text(encoding='utf-8'))
        if m.get('status')=='ACQUIRED' and m.get('release')==spec:
            if any(checksum(local_path(root,root/f['path']))!=f['sha256'] for f in m['files']):raise ValueError('추가 추적 원본 지문 불일치')
            if spec['league']=='KBO':validate_kbo(m['files'])
            return p
    folder=base/(name+'-'+secrets.token_hex(4));private(folder,directory=True)
    m={'schema':'tracking-release-v1','status':'ACQUIRING','release':spec,'created_at':utc_now(),'files':[],
       'raw_redistribution':False,'rights_status':'PUBLIC_DISTRIBUTION_UPSTREAM_UNVERIFIED'}
    target=folder/'manifest.json';write_json(target,m)
    if name.startswith('mlb'):
        query='?datasetVersionNumber='+str(spec['version'])
        meta=folder/'metadata.json';download('https://www.kaggle.com/api/v1/datasets/view/'+spec['repository'],meta,4*1024*1024)
        listing=folder/'file-list.json';download('https://www.kaggle.com/api/v1/datasets/list/'+spec['repository']+query,listing,4*1024*1024)
        expected={f['name']:int(f['totalBytes']) for f in json.loads(listing.read_text())['datasetFiles']}
        archive=folder/'source.zip';download('https://www.kaggle.com/api/v1/datasets/download/'+spec['repository']+query,archive,spec['limit'])
        print(name+' 원본 ZIP 확보',flush=True)
        with ZipFile(archive) as z:
            if len(z.infolist())>30:raise ValueError('배포 멤버 수 한도')
            seen=set()
            for info in z.infolist():
                if info.is_dir():continue
                if ('/' in info.filename or '\\' in info.filename or info.filename in ('.','..') or info.filename in seen or
                    info.external_attr>>16&0o170000==0o120000 or info.flag_bits&1 or info.filename not in expected or info.file_size!=expected[info.filename]):raise ValueError('배포 파일 목록 불일치')
                seen.add(info.filename)
                path=folder/info.filename
                with z.open(info) as src,open_private(path) as out:
                    while b:=src.read(1024*1024):out.write(b)
                m['files'].append({'path':str(path.relative_to(root)),'name':info.filename,'sha256':checksum(path),'bytes':path.stat().st_size})
                print(name+' · '+info.filename,flush=True)
        m.update(archive_sha256=checksum(archive),metadata_sha256=checksum(meta),publisher_license=json.loads(meta.read_text()).get('licenseName'))
    else:
        for file,file_id in KBO_FILES.items():
            path=folder/file;url='https://drive.google.com/uc?'+urlencode({'export':'download','id':file_id})
            download(url,path,8*1024*1024,hosts={'drive.google.com','drive.usercontent.google.com'})
            with path.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f)
                if not {'location_x_norm','location_z_norm','pitch_key','balls','strikes'}<=set(reader.fieldnames or []):raise ValueError('KBO 좌표 CSV가 아닌 응답')
                rows=sum(1 for _ in reader)
            m['files'].append({'path':str(path.relative_to(root)),'name':file,'file_id':file_id,'source_url':url,'sha256':checksum(path),'bytes':path.stat().st_size,'rows':rows})
            print(name+' · '+file+' · '+str(rows)+'투구',flush=True)
        validate_kbo(m['files'])
        for file in ('README.md','docs/STATCAST_COMPARISON.md','docs/DATA_DICTIONARY.md'):
            path=folder/file.split('/')[-1];download('https://raw.githubusercontent.com/'+spec['repository']+'/'+spec['revision']+'/'+file,path,2*1024*1024)
        m['definitions_sha256']=checksum(folder/'STATCAST_COMPARISON.md')
    m['status']='ACQUIRED';m['bytes']=sum(f['bytes'] for f in m['files']);write_json(target,m);return target
