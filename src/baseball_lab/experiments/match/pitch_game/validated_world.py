"""Packaged validation results bound to exact data and model implementation."""
import gzip,hashlib,inspect,json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from .corpus_world import Cohort,legal_movement,EVENTS,walk
from .directional_contact import ContactModel,CONTACT,AIMS

ASSET='modern-world-validation-v1.json.gz'
ASSET_SHA256='1078b187e9a84930bc838ddebbb1da798f810f3ee99ecc28ced1e2ff9dd19127'


def algorithm_hash():
    source=''.join(inspect.getsource(v) for v in (Cohort,ContactModel,legal_movement,walk))+repr((EVENTS,CONTACT,AIMS))
    return hashlib.sha256(source.encode()).hexdigest()


@lru_cache(maxsize=1)
def load(asset_sha):
    body=files('baseball_lab').joinpath('data/resources',ASSET).read_bytes()
    if hashlib.sha256(body).hexdigest()!=ASSET_SHA256:raise ValueError('보관된 모형 검사 결과의 지문 불일치')
    d=json.loads(gzip.decompress(body))
    if d['data_sha256']!=asset_sha or d['algorithm_sha256']!=algorithm_hash():return None
    return d['cohorts']


def prepare(output):
    from .modern_world import data,ASSET_SHA256 as DATA_SHA
    output=Path(output)
    if output.exists():raise FileExistsError('기존 검사 기록 덮어쓰기 거부')
    d=data();values={}
    for k,c in d['cohorts'].items():
        pitch=Cohort(c);contact=ContactModel(d['contacts'][k])
        values[k]={'pitch':{n:getattr(pitch,n) for n in ('strength','metrics','movement_metrics','running_metrics')},
                   'contact':{n:getattr(contact,n) for n in ('strength','metrics')}}
    body=gzip.compress(json.dumps({'schema':'validated-modern-world-v1','data_sha256':DATA_SHA,'algorithm_sha256':algorithm_hash(),'cohorts':values},separators=(',',':')).encode(),mtime=0)
    output.write_bytes(body);return hashlib.sha256(body).hexdigest()
