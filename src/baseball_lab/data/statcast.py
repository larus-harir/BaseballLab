"""Bounded official acquisition and a strict, auditable Statcast CSV adapter."""
import csv
import math
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib import request, parse, robotparser

from .lineage import RawSource, SourceStatus, checksum, content_hash, utc_now, write_json

SCHEMA = 'statcast-normalized-v1'
OFFICIAL = 'https://baseballsavant.mlb.com'
USER_AGENT = 'BaseballAILab/0.4 (limited local research; no redistribution)'
REQUIRED = {'game_date','game_pk','at_bat_number','pitch_number','balls','strikes','pitch_type','description','events','game_type'}
OPTIONAL_NUMERIC = ('plate_x','plate_z','sz_top','sz_bot','release_speed','release_spin_rate','launch_speed','launch_angle')
SWING = {'swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play'}
TAKE = {'ball','blocked_ball','called_strike','pitchout'}
HITS = {'single','double','triple','home_run'}
OUTS = {'field_out','force_out','grounded_into_double_play','double_play','triple_play','sac_fly','fielders_choice_out'}


def request_bytes(url, *, limit=32*1024*1024, timeout=60):
    req = request.Request(url, headers={'User-Agent': USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        data = response.read(limit+1)
    if len(data) > limit:
        raise ValueError('다운로드 상한 초과. 날짜 범위를 줄이세요.')
    return data


def acquire(start: str, end: str, output: Path, *, usage_note: str, authorization_reference: str | None = None):
    if not authorization_reference or not authorization_reference.strip():
        raise PermissionError('공식 이용약관에 자동 스크립트 수집 제한이 있습니다. 기본 경로는 공식 CSV 내보내기 후 업로드입니다. 별도 자동 수집 허용 근거가 있을 때만 --authorization-reference를 사용하세요.')
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first or (last-first).days > 13:
        raise ValueError('한 번에 최대 14일, 시작일 <= 종료일이어야 합니다.')
    if not usage_note.strip():
        raise ValueError('사용조건 확인 내용을 --usage-note로 남기세요.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sources = []
    try:
        robots_bytes = request_bytes(OFFICIAL+'/robots.txt', limit=1024*1024)
        if b'user-agent' not in robots_bytes.lower() or b'<html' in robots_bytes[:500].lower():
            raise ValueError('robots.txt 확인 불가. 공식 수동 내보내기를 사용하세요.')
        robots = robotparser.RobotFileParser()
        robots.parse(robots_bytes.decode('utf-8', errors='replace').splitlines())
        (output/'robots.txt').write_bytes(robots_bytes)
        for offset in range((last-first).days+1):
            day = (first+timedelta(days=offset)).isoformat()
            params = {'all':'true','type':'details','player_type':'pitcher','hfGT':'R|',
                      'game_date_gt':day,'game_date_lt':day,'group_by':'name','min_pitches':'0','min_results':'0'}
            url = OFFICIAL+'/statcast_search/csv?'+parse.urlencode(params)
            if not robots.can_fetch(USER_AGENT, url):
                raise PermissionError('robots.txt에서 이 수집 경로를 허용하지 않습니다. 공식 CSV 내보내기를 사용하세요.')
            path = output/f'statcast_{day}.csv'
            if path.exists():
                raise FileExistsError(f'기존 원본을 덮어쓰지 않습니다: {path}')
            data = request_bytes(url)
            # Reject HTML/errors before publishing a raw file as a dataset.
            text = data.decode('utf-8-sig')
            header = csv.DictReader(text.splitlines()).fieldnames or []
            if not REQUIRED.issubset(header):
                raise ValueError('Statcast CSV가 아닌 응답 또는 필수 필드 누락')
            path.write_bytes(data)
            sources.append(RawSource('MLB Baseball Savant Statcast', url, str(path.resolve()), utc_now(),
                           checksum(path), SourceStatus.REAL_OBSERVED.value,
                           usage_note+'; user-declared automation authorization: '+authorization_reference+'; raw redistribution disabled; https://www.mlb.com/official-information/terms-of-use',
                           'official_https_csv').to_dict())
            write_json(output/'acquisition.json', {'status':'partial', 'sources':sources,'requested_dates':[start,end]})
            if offset < (last-first).days:
                time.sleep(max(1., robots.crawl_delay(USER_AGENT) or 0))
    except Exception as exc:
        write_json(output/'acquisition_failure.json', {'status':'DATA_REQUIRED', 'observed_at':utc_now(),
                   'url':OFFICIAL, 'error_type':type(exc).__name__, 'error':str(exc), 'partial_sources':sources,
                   'research_executed':False})
        raise
    result = {'status':'acquired', 'sources':sources, 'requested_dates':[start,end],
              'robots_checksum':checksum(output/'robots.txt'), 'source_status':'REAL_OBSERVED'}
    write_json(output/'acquisition.json', result)
    return result


def manual_source(path: Path, source_url: str, usage_note: str, acquired_at: str):
    if parse.urlparse(source_url).hostname != 'baseballsavant.mlb.com' or not source_url.startswith('https://'):
        raise ValueError('공식 Baseball Savant HTTPS 내보내기 URL이 필요합니다.')
    if not usage_note.strip() or not acquired_at.strip():
        raise ValueError('직접 내보낸 파일의 사용조건·획득 시각을 기록하세요.')
    if datetime.fromisoformat(acquired_at).tzinfo is None:
        raise ValueError('획득 시각에 시간대(예: +09:00)를 포함하세요.')
    return RawSource('MLB Baseball Savant Statcast (user export)', source_url, str(path.resolve()), acquired_at,
                     checksum(path), 'REAL_OBSERVED', usage_note+'; redistribution not granted', 'user_attested_export')


def numeric(value):
    if value is None or value.strip().lower() in ('','null','nan','na'):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def classify(row):
    description, terminal = row['description'], row['events']
    if description in TAKE:
        return 'take', 'strike' if description == 'called_strike' else 'ball'
    if description not in SWING:
        return None
    if description in ('swinging_strike','swinging_strike_blocked','foul_tip'):
        return 'swing','strike'
    if description == 'foul':
        return 'swing','foul'
    if terminal in HITS:
        return 'swing',terminal
    if terminal in OUTS:
        return 'swing','out'
    if terminal in ('field_error','fielders_choice'):
        return 'swing','reached'
    return None


def audit(sources: list[RawSource], output: Path):
    if not sources:
        raise ValueError('실제 원본이 없습니다. DATA_REQUIRED')
    records, seen, raw_rows = [], {}, 0
    missing, exclusions, dates, games = Counter(), Counter(), set(), set()
    for source in sources:
        path = source.verify()
        with path.open(encoding='utf-8-sig', newline='') as file:
            reader = csv.DictReader(file)
            if not REQUIRED.issubset(reader.fieldnames or []):
                raise ValueError(f'필수 CSV 필드 누락: {sorted(REQUIRED-set(reader.fieldnames or []))}')
            for row in reader:
                raw_rows += 1
                for column in sorted(REQUIRED | set(OPTIONAL_NUMERIC)):
                    missing[column] += not row.get(column, '').strip() or row.get(column, '').strip().lower() in ('null','nan')
                try:
                    day = date.fromisoformat(row['game_date'][:10]).isoformat()
                    balls, strikes = int(row['balls']), int(row['strikes'])
                    game_id, pa, pitch = int(row['game_pk']), int(row['at_bat_number']), int(row['pitch_number'])
                    if not 0 <= balls <= 3 or not 0 <= strikes <= 2 or min(game_id,pa,pitch) < 1:
                        raise ValueError('invalid count/key')
                    values = {key:numeric(row.get(key,'')) for key in OPTIONAL_NUMERIC}
                    if values['sz_top'] is not None and values['sz_bot'] is not None and values['sz_top'] <= values['sz_bot']:
                        raise ValueError('inverted zone')
                except (ValueError,TypeError):
                    exclusions['invalid_key_count_or_numeric'] += 1
                    continue
                record_id = f'{game_id}:{pa}:{pitch}'
                fingerprint = content_hash({k: row.get(k,'') for k in sorted(REQUIRED | set(OPTIONAL_NUMERIC))})
                if record_id in seen:
                    if seen[record_id] != fingerprint:
                        raise ValueError(f'동일 투구 ID의 내용 충돌: {record_id}')
                    exclusions['duplicate'] += 1
                    continue
                seen[record_id] = fingerprint
                if row['game_type'] != 'R':
                    exclusions['not_regular_season'] += 1
                    continue
                classified = classify(row)
                if not classified or not row['pitch_type'].strip():
                    exclusions['unsupported_description_event_or_pitch_type'] += 1
                    continue
                action, event = classified
                dates.add(day); games.add(game_id)
                record = {'record_id':record_id,'game_date':day,'game_pk':game_id,'at_bat_number':pa,'pitch_number':pitch,
                          'balls':balls,'strikes':strikes,'pitch_type':row['pitch_type'], 'observed_action':action,
                          'event':event,'description':row['description'],'recorded_pa_event':row['events'],
                          'source_status':source.source_status,'source_checksum':source.raw_file_checksum, **values}
                record['release_speed_kmh'] = values['release_speed']*1.609344 if values['release_speed'] is not None else None
                records.append(record)
    if not records:
        raise ValueError('필터 후 사용 가능한 실제 투구가 없습니다.')
    records.sort(key=lambda r:(r['game_date'],r['game_pk'],r['at_bat_number'],r['pitch_number']))
    consistency = 0
    for previous,current in zip(records,records[1:]):
        if (previous['game_pk'],previous['at_bat_number']) != (current['game_pk'],current['at_bat_number']):
            continue
        if previous['pitch_number']+1 != current['pitch_number']:
            continue  # Excluded unsupported pitches cannot be silently reconstructed.
        event=previous['event']
        b,s=previous['balls'],previous['strikes']
        expected = (b+1,s) if event=='ball' else (b,s+1) if event=='strike' else (b,min(s+1,2)) if event=='foul' else None
        if expected is not None and (current['balls'],current['strikes']) != expected:
            consistency += 1
    if len({day[:4] for day in dates}) != 1:
        raise ValueError('연도별 센서/기록 정의를 검토하기 전에는 여러 시즌을 합치지 않습니다.')
    status = 'MOCK_TEST_ONLY' if any(s.source_status=='MOCK_TEST_ONLY' for s in sources) else (
             'REAL_OBSERVED' if all(s.source_status=='REAL_OBSERVED' for s in sources) else 'UNVERIFIED_ASSUMPTION')
    manifest = {'schema_version':SCHEMA,'source_status':status,'sources':[s.to_dict() for s in sources],
                'raw_rows':raw_rows,'used_rows':len(records),'games':len(games),'date_range':[min(dates),max(dates)],
                'missingness_report':{k:{'missing':v,'denominator':raw_rows,'rate':v/raw_rows} for k,v in missing.items()},
                'exclusions':dict(exclusions),'count_sequence_mismatches':consistency,
                'units':{'plate_x':'feet, catcher perspective; native sign','plate_z':'feet','sz_top':'feet','sz_bot':'feet',
                         'release_speed':'mph','release_speed_kmh':'km/h, mph*1.609344','release_spin_rate':'rpm',
                         'launch_speed':'mph','launch_angle':'degrees'},
                'filters':'Regular season if acquisition used hfGT=R; supported non-bunt take/swing physical pitches only; see exclusions',
                'unsupported_features':['intended pitch location','contact-vs-power intention','bunt','effort/fatigue causal effect','fielding motion','ball flight trajectory','KBO'],
                'normalized_checksum':content_hash(records),'created_at':utc_now()}
    manifest['dataset_version'] = content_hash({k:manifest[k] for k in ('schema_version','normalized_checksum','source_status')})
    output=Path(output)
    write_json(output/'dataset.json', {'manifest':manifest,'records':records})
    write_json(output/'quality.json',manifest)
    return {'manifest':manifest,'records':records}


def load_dataset(path):
    import json
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    manifest,records=payload['manifest'],payload['records']
    if manifest['schema_version']!=SCHEMA or content_hash(records)!=manifest['normalized_checksum']:
        raise ValueError('정규화 자료 무결성 또는 스키마 불일치')
    for source in manifest['sources']:
        RawSource(**source).verify()
    expected_version=content_hash({k:manifest[k] for k in ('schema_version','normalized_checksum','source_status')})
    if manifest['dataset_version'] != expected_version:
        raise ValueError('데이터셋 버전 무결성 불일치')
    if manifest['used_rows'] != len(records):
        raise ValueError('정규화 행 수 불일치')
    if any(r['source_status']!=manifest['source_status'] for r in records):
        raise ValueError('자료 상태가 혼합되었거나 변경됨')
    return payload
