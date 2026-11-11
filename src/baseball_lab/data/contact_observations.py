"""Read-only views of recorded contact and pitch-result codes.

The observed codes describe human plays. They are never transplanted into a
simulated PA as a measured trajectory, speed, pitch type or strike-zone point.
Only the registered, checksum-verified Retrosheet release is read here.
"""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import threading

from baseball_lab.data.catalog import DatasetCatalog
from baseball_lab.data.lineage import content_hash

VERSION = 'retrosheet-contact-observations-v1'
TYPE_LABELS = {'BG': '번트 땅볼', 'BP': '번트 팝업', 'BL': '번트 직선타',
               'G': '땅볼', 'P': '팝업', 'F': '뜬공', 'L': '직선타'}
FIELDER_LABELS = {'1': '투수', '2': '포수', '3': '1루수', '4': '2루수',
                  '5': '3루수', '6': '유격수', '7': '좌익수', '8': '중견수', '9': '우익수'}
PITCH_RESULT_LABELS = {'B':'볼', 'C':'루킹 스트라이크', 'F':'파울', 'H':'몸에 맞는 공',
    'I':'고의 볼', 'K':'스트라이크(종류 미상)', 'L':'번트 파울', 'M':'번트 헛스윙',
    'O':'번트 파울팁', 'P':'피치아웃', 'Q':'피치아웃에 스윙', 'R':'피치아웃 파울',
    'S':'헛스윙 스트라이크', 'T':'파울팁', 'U':'투구 정보 불명·누락',
    'X':'타구 인플레이', 'Y':'피치아웃 타구 인플레이'}
_OTHER_SEQUENCE_CODES = {'A':('automatic_call','자동 스트라이크'),
    'V':('automatic_call','자동 볼 판정'), 'N':('no_pitch','투구 없음'),
    '1':('pickoff_throw','1루 견제'), '2':('pickoff_throw','2루 견제'), '3':('pickoff_throw','3루 견제'),
    '+':('annotation','포수 견제구 뒤 표식'), '*':('annotation','다음 투구의 포수 블로킹 표식'),
    '.':('annotation','타자 외 플레이 표식'), '>':('annotation','주자 출발 표식')}
_UNAVAILABLE = ('', '0', '?', '??')
_INDEX_GUARD = threading.Lock()
_INDEX_LOCKS = {}


def _new():
    return {'pa': 0, 'contact': 0, 'home_runs': 0, 'home_runs_in_bip': 0, 'pitch_sequences_present': 0,
            'types': Counter(), 'locations': Counter(), 'fielders': Counter(),
            'type_unknown': 0, 'location_unknown': 0, 'fielder_unknown': 0,
            'sequence_examples': [], 'contact_examples': []}


def _add(value, row):
    """Only completed PA rows; the denominator never includes steals/pickoffs."""
    value['pa'] += 1
    value['home_runs'] += row.get('hr') == '1'
    sequence = row.get('pitches', '').strip()
    if sequence:
        value['pitch_sequences_present'] += 1
        if len(value['sequence_examples']) < 4:
            value['sequence_examples'].append({'game_id': row['gid'], 'play_number': row['pn'],
                                               'pitch_result_codes': sequence,
                                               'event_code': row['event']})
    if row.get('bip') != '1':
        return
    value['contact'] += 1
    value['home_runs_in_bip'] += row.get('hr') == '1'
    kind = row.get('hittype', '').strip()
    if kind in TYPE_LABELS:
        value['types'][kind] += 1
    else:
        value['type_unknown'] += 1
    location = row.get('loc', '').strip()
    if location not in _UNAVAILABLE:
        value['locations'][location] += 1
    else:
        value['location_unknown'] += 1
    fielder = row.get('firstf', '').strip()
    if fielder in FIELDER_LABELS:
        value['fielders'][fielder] += 1
    else:
        value['fielder_unknown'] += 1
    if len(value['contact_examples']) < 4:
        value['contact_examples'].append({'game_id': row['gid'], 'play_number': row['pn'],
            'event_code': row['event'], 'recorded_type': kind or None,
            'recorded_location_code': location if location not in _UNAVAILABLE else None,
            'first_fielder_position': fielder if fielder in FIELDER_LABELS else None})


def _aggregate(rows):
    total = _new(); batters = {}; pitchers = {}; seen = set()
    for row in rows:
        if row.get('pa') != '1':
            continue
        identity = (row['gid'], row['pn'])
        if identity in seen:
            raise ValueError('관측 타석 ID가 중복되어 타구 자료를 집계하지 않았습니다.')
        if not row.get('batter') or not row.get('pitcher'):
            raise ValueError('타자·투수 식별자가 없는 관측 타석입니다.')
        seen.add(identity)
        _add(total, row)
        for target,player in ((batters,row['batter']),(pitchers,row['pitcher'])):
            if player not in target:target[player] = _new()
            _add(target[player], row)
    return {'season': total, 'batter': batters, 'pitcher': pitchers}


@lru_cache(maxsize=8)
def _index(root, year, signature):
    catalog = DatasetCatalog(root)
    value = _aggregate(catalog.iter_plays(year))
    after = catalog.describe('match', year)
    if not after['ready'] or content_hash(after['metadata']['sha256']) != signature:
        raise ValueError('읽는 동안 공식 원본이 바뀌어 타구 집계를 취소했습니다.')
    return value


def _shared_index(root,year,signature):
    # A role change during the first scan must join it, not start another full
    # CSV scan. Separate seasons and normal page/status requests remain free.
    with _INDEX_GUARD:
        guard=_INDEX_LOCKS.setdefault((root,year),threading.Lock())
    with guard:
        return _index(root,year,signature)


def summarize(root, season, *, role=None, player_id=None):
    """Return season, one batter, or one pitcher's actual completed-PA cohort.

    No download, repair, write, parameter fit, or simulation is performed. The
    first request scans the verified season once; later views reuse the index.
    """
    if role not in (None, 'batter', 'pitcher') or (role is None) != (player_id is None):
        raise ValueError('시즌 전체 또는 타자·투수 한 명의 관측 범위를 선택하세요.')
    if player_id is not None and (not isinstance(player_id, str) or not player_id or len(player_id) > 80):
        raise ValueError('선수 식별자를 확인하세요.')
    catalog = DatasetCatalog(root)
    descriptor = catalog.describe('match', season)
    if not descriptor['ready']:
        raise ValueError('이 시즌의 검증된 플레이별 기록이 없습니다.')
    metadata = descriptor['metadata']
    if metadata['status'] != 'REAL_OBSERVED':
        raise ValueError('실제 관측 상태의 공식 자료만 표시합니다.')
    signature = content_hash(metadata['sha256'])
    data = _shared_index(str(Path(root).resolve()), season, signature)
    if role is None:
        value = data['season']
    else:
        value = data[role].get(player_id)
        if value is None:
            raise ValueError('선택한 선수의 완료 타석 관측 기록이 없습니다.')
    contact = value['contact']; pa = value['pa']
    return {'schema': VERSION, 'source_status': 'REAL_OBSERVED', 'season': season,
        'scope': {'role': role or 'season', 'player_id': player_id,
                  'definition': '선택한 시즌·선수가 실제로 치르거나 상대한 완료 타석'},
        'source': {'provider': 'Retrosheet', 'url': 'https://www.retrosheet.org/downloads/plays.html',
                   'definition_urls': ['https://www.retrosheet.org/downloads/plays.html',
                                       'https://www.retrosheet.org/eventfile.htm',
                                       'https://www.retrosheet.org/location.htm'],
                   'files': metadata['sha256'], 'fingerprint': signature, 'credit': metadata['license']},
        'counts': {'completed_pa': pa, 'batted_ball_pa': contact,
                   'home_run_pa':value['home_runs'],'home_run_pa_in_bip':value['home_runs_in_bip'],
                   'home_run_pa_outside_bip':value['home_runs']-value['home_runs_in_bip'],
                   'pitch_sequence_present_pa': value['pitch_sequences_present']},
        'batted_ball_types': [{'code': k, 'label': TYPE_LABELS[k], 'n': v}
                              for k,v in sorted(value['types'].items())],
        'recorded_location_codes': [{'code': k, 'n': v} for k,v in value['locations'].most_common()],
        'first_fielder_positions': [{'code': k, 'label': FIELDER_LABELS[k], 'n': v}
                                    for k,v in sorted(value['fielders'].items())],
        'missing': {'batted_ball_type': value['type_unknown'],
                    'recorded_location_code': value['location_unknown'],
                    'first_fielder': value['fielder_unknown'],
                    'pitch_sequence_pa': pa-value['pitch_sequences_present']},
        'contact_examples': [dict(x) for x in value['contact_examples']],
        'pitch_sequence_examples': [{**x,'tokens':decode_pitch_sequence(x['pitch_result_codes'])}
                                    for x in value['sequence_examples']],
        'capabilities': {'observed_batted_ball_type': True, 'recorded_location_code': True,
                          'first_fielder_position': True, 'pitch_result_sequence': True,
                          'measured_exit_velocity': False, 'launch_angle': False,
                          'measured_pitch_velocity': False, 'pitch_type': False,
                          'plate_coordinates': False, 'ball_trajectory': False},
        'interpretation': '실제 인간 경기의 관측 기록입니다. 가상 대결의 타구 방향·속도 예측이 아닙니다.',
        'contact_definition': '완료 타석 중 원천 bip=1인 타석만 집계합니다. 모든 타구가 아니라 원천의 인플레이 범위이며 대부분의 홈런은 이 범위 밖입니다. 전체 홈런·범위 내 홈런 수를 따로 제공합니다.',
        'location_note': 'loc는 원천의 타구 위치 코드입니다. + 같은 원천 접미를 보존하며 미확인 접미를 해석하거나 각도·미터 좌표로 변환하지 않았습니다. firstf는 처음 처리한 수비 위치이며 착탄 지점이 아닙니다.',
        'pitch_note': 'pitches는 해당 플레이의 투구 결과 코드열입니다. 구종·구속·코스를 측정한 기록이 아닙니다.'}


def observations(root, season, batter):
    """Fixed batter-cohort adapter for the read-only web endpoint."""
    return summarize(root, season, role='batter', player_id=batter)


def decode_pitch_sequence(sequence):
    """Decode documented result/annotation symbols, never fabricate pitch count.

    A/V are automatic calls; N means no pitch; >, *, ., + are annotations;
    1/2/3 are pickoffs. Their character positions are not pitch numbers.
    """
    result=[]
    for index,code in enumerate(sequence):
        if code in PITCH_RESULT_LABELS:kind,label='pitch_result',PITCH_RESULT_LABELS[code]
        else:kind,label=_OTHER_SEQUENCE_CODES.get(code,('unknown','미분류 코드'))
        result.append({'sequence_index':index+1,'code':code,'kind':kind,'label':label})
    return result
