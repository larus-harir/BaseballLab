"""Application-included season records compiled from the supplied assignment.

The original CSVs, Python program and report are not runtime requirements.
The bundle contains only the identity and season counts used by the shared
engine. It preserves the original source/version and its unverified status.
"""
import gzip
import hashlib
import io
import json
from importlib.resources import files
import threading

from baseball_lab.data.lineage import content_hash,utc_now
from baseball_lab.matchup.catalog import identity,LEGACY_SHA,SCHEMA

BUNDLE_NAME='kbo-seasons-v1.json.gz'
BUNDLE_SHA256='4f2b004ec985be8ee757259a43b16be4f14e04d8af814b3d46bb2c2652dcd457'
BUNDLE_SCHEMA='eramatch-bundled-seasons-v1'
PROFILE_FIELDS=frozenset(('id','player_id','name','season','league','role','teams','counts',
    'events','issues','legacy_row','legacy_source_row','legacy_eligible','normalized_eligible',
    'team_rows','status','league_rates'))
COUNT_FIELDS=frozenset(('PA','AB','H','2B','3B','HR','SO','BB','HP','SH','SF','TBF','IP_OUTS'))
_CACHE=None
_LOCK=threading.RLock()


def validate_public_fields(catalog):
    """Allow only matchup inputs, never biographical columns from source CSVs."""
    for profile in catalog['profiles'].values():
        if set(profile)-PROFILE_FIELDS:raise ValueError('기본 기록에 대결과 무관한 선수 항목이 있습니다.')
        for key in ('counts','legacy_row'):
            if profile.get(key) is not None and set(profile[key])-COUNT_FIELDS:
                raise ValueError('기본 기록에 허용하지 않은 성적 항목이 있습니다.')


def load_builtin():
    global _CACHE
    resource=files(__package__).joinpath('resources',BUNDLE_NAME)
    try:content=resource.read_bytes()
    except OSError as exc:raise ValueError('EraMatch 기본 기록이 없습니다. 프로그램을 업데이트하거나 다시 설치하세요.') from exc
    if len(content)>4*1024*1024 or hashlib.sha256(content).hexdigest()!=BUNDLE_SHA256:
        raise ValueError('EraMatch 기본 기록의 버전이 다릅니다. 프로그램을 업데이트하거나 다시 설치하세요.')
    with _LOCK:
        if _CACHE is not None:return _CACHE[0]
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as file:raw=file.read(32*1024*1024+1)
        if len(raw)>32*1024*1024:raise ValueError('EraMatch 기본 기록 크기가 올바르지 않습니다.')
        payload=json.loads(raw)
        catalog=payload['catalog']
        if payload['schema']!=BUNDLE_SCHEMA or payload['provenance']['archive_sha256']!=LEGACY_SHA:
            raise ValueError('EraMatch 제공 자료의 출처 버전이 다릅니다.')
        if catalog.get('schema')!=SCHEMA or content_hash(identity(catalog))!=catalog.get('dataset_id'):
            raise ValueError('EraMatch 기본 기록의 내용 검사를 통과하지 못했습니다.')
        validate_public_fields(catalog)
        if catalog['source']['status']!='LEGACY_UNVERIFIED':raise ValueError('과제 자료의 검증 상태를 확인하세요.')
        _CACHE=(catalog,utc_now())
        return catalog


def verification():
    load_builtin()
    with _LOCK:timestamp=_CACHE[1]
    return {'verified_at':timestamp,'name':BUNDLE_NAME,'sha256':BUNDLE_SHA256,
            'scope':'bundled aggregate file hash and catalog identity; original input hashes checked at compilation'}
