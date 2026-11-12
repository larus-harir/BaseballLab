"""Small application-included aggregates; never a replacement for observed turns."""
from functools import lru_cache
import gzip
import hashlib
from importlib.resources import files
import json

INDEX_SHA256='cccf559c4c96472847d12cb3abf07ad55f3340f164bd197e8fcafac07f7a81db'


@lru_cache(maxsize=1)
def index():
    # Git on Windows may convert LF to CRLF. Verify canonical LF bytes;
    # all other content changes must still fail the pinned checksum.
    raw=files(__package__).joinpath('resources/index.json').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=INDEX_SHA256:raise ValueError('앱 포함 자료의 출처 목록이 변경됐습니다.')
    data=json.loads(raw)
    if data['schema']!='compact-source-index-v1':raise ValueError('지원하지 않는 기본 자료 버전입니다.')
    return data


@lru_cache(maxsize=1)
def players():
    raw=files(__package__).joinpath('resources/players.json.gz').read_bytes()
    if len(raw)>8*1024*1024 or hashlib.sha256(raw).hexdigest()!=index()['players_sha256']:raise ValueError('앱 포함 선수 집계의 지문이 다릅니다.')
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:body=f.read(200*1024*1024+1)
    if len(body)>200*1024*1024:raise ValueError('선수 집계 크기 한도를 넘었습니다.')
    data=json.loads(body)
    if data['schema']!='compact-player-aggregates-v1' or len(data['rows'])!=index()['players_rows']:raise ValueError('선수 집계 버전이 다릅니다.')
    return data['rows']


def periods():
    return {year:{'start':m['start'],'end':m['end']} for year,m in index()['mlb'].items()}


def npb_before(cutoff):
    from baseball_lab.experiments.match.team_win.mixed import rates,EVENTS
    source=index()['npb'];days=sorted(d for d in source['daily_counts'] if d<cutoff)
    counts={k:sum(source['daily_counts'][d][k] for d in days) for k in EVENTS}
    if not days:raise ValueError('검사 시작 전 NPB 정규시즌 관측이 없습니다. NPB를 포함하려면 2025년 수집 기간을 권장합니다.')
    return {'counts':counts,'rates':rates(counts),'dates':[days[0],days[-1]],'cutoff_exclusive':cutoff,
            'provider':'armstjc-npb-spaia','source_hashes':source['source_hashes'],'rights_status':source['rights_status'],
            'date_semantics':'provider game_date; historical publication/correction availability is not independently verified',
            'attribution':source['attribution'],'scope':'Only observed regular-season batting games before validation; no NPB runner-transition claim.'}


MLB_NAMES_SHA256='9775ba1d28edbdfa131c129aa7933c4888c2b285e31974124ed96ee1731ff616'


@lru_cache(maxsize=1)
def mlb_names():
    raw=files(__package__).joinpath('resources/mlb-names-v1.json.gz').read_bytes()
    if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=MLB_NAMES_SHA256:raise ValueError('MLB 선수 이름 자료의 지문이 다릅니다.')
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:body=f.read(4*1024*1024+1)
    if len(body)>4*1024*1024:raise ValueError('선수 이름 자료 크기 한도를 넘었습니다.')
    payload=json.loads(body)
    if payload['schema']!='retrosheet-player-display-names-v1':raise ValueError('선수 이름 자료 버전이 다릅니다.')
    return payload['names']
