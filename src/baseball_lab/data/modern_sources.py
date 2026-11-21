"""Fixed supplemental observations, downloaded only in the preparation environment."""
from pathlib import Path
import secrets
from .pitch_sources import download
from .lineage import checksum,write_json
from .protection import private
from .warehouse import local_path

REPOSITORY='slothman3878/kbo_playbyplay'
REVISION='e2cd82b064902a4d42de128de6bf9043e62c6d80'
PITCH_FILES={2023:'2e2cbd28aaf4d39bfa1581be53f59bcf8525a11309468940b821182e46587bb6',2024:'48adc9682c10b17dfb525aba53e2d61278631cd63bc93bb7df2ae3999681b01c',2025:'5f6204ca1370347ab562b1c56a9d58fcb0774c1118ac65f611ffef29c6d09f78',2026:'ca2efc272878aa39310961861bed9ec18e93b003815c113558b5bc488af83193'}
HOSTS={'huggingface.co','us.aws.cdn.hf.co','cdn-lfs.huggingface.co','cas-bridge.xethub.hf.co'}


def collect_history(root):
    root=Path(root).resolve();base=local_path(root,root/'data/local/modern-releases');private(base,directory=True)
    revision='b62930452642e6eb290a78302497942c8065960d'
    sha='ce081e547a80c688ae02d996525e59fb934db881aeb6ce80418f5e1c197c5b20'
    folder=base/('npb-history-'+revision[:8]);private(folder,directory=True);p=folder/'standings.csv'
    url='https://huggingface.co/datasets/yasumorishima/npb-stats/resolve/'+revision+'/data/raw/npb_standings_2015_2025.csv'
    if not p.exists():download(url,p,128*1024,hosts=HOSTS)
    if checksum(p)!=sha:raise ValueError('NPB 과거 시즌 기록 지문 불일치')
    target=folder/'manifest.json'
    if not target.exists():write_json(target,{'status':'ACQUIRED','repository':'yasumorishima/npb-stats','revision':revision,'source_url':url,
        'credit':'Public NPB team standings by yasumorishima; publisher license unspecified, upstream rights unverified',
        'raw_redistribution':False,'files':[{'path':str(p.relative_to(root)),'sha256':sha,'bytes':p.stat().st_size}]})
    return target


def collect(root):
    root=Path(root).resolve();base=local_path(root,root/'data/local/modern-releases');private(base,directory=True)
    for p in base.glob('*/manifest.json'):
        m=__import__('json').loads(p.read_text())
        if m.get('revision')==REVISION and m.get('status')=='ACQUIRED':
            if len(m.get('files',[]))!=len(PITCH_FILES) or {f.get('year'):f.get('sha256') for f in m['files']}!=PITCH_FILES:
                raise ValueError('KBO 고정 배포 파일 목록이 불완전하거나 검토 버전과 다릅니다.')
            if all(checksum(local_path(root,root/f['path']))==f['sha256'] for f in m['files']):return p
            raise ValueError('현대 야구 추가 원본의 지문 불일치')
    folder=base/('kbo-'+secrets.token_hex(4));private(folder,directory=True)
    m={'schema':'modern-release-v1','status':'ACQUIRING','repository':REPOSITORY,'revision':REVISION,'files':[],
       'credit':'KBO Play-by-Play by slothman3878, CC BY 4.0; NAVER/Daum-derived, upstream rights unverified',
       'source_url':'https://huggingface.co/datasets/'+REPOSITORY,'raw_redistribution':False}
    target=folder/'manifest.json';write_json(target,m)
    for year,sha in PITCH_FILES.items():
        name=f'v0/kbo_pbp_{year}.parquet';p=folder/Path(name).name
        download('https://huggingface.co/datasets/'+REPOSITORY+'/resolve/'+REVISION+'/'+name+'?download=true',p,24*1024*1024,hosts=HOSTS)
        if checksum(p)!=sha:raise ValueError('고정된 KBO Parquet 원본과 다릅니다.')
        m['files'].append({'path':str(p.relative_to(root)),'year':year,'sha256':sha,'bytes':p.stat().st_size})
        print('KBO 실제 투구 확보',year,flush=True)
    for name in ('README.md','v0/schema.yaml'):
        p=folder/Path(name).name;download('https://huggingface.co/datasets/'+REPOSITORY+'/resolve/'+REVISION+'/'+name,p,128*1024,hosts=HOSTS)
        m.setdefault('definitions',[]).append({'name':name,'sha256':checksum(p)})
    m['status']='ACQUIRED';write_json(target,m);return target
