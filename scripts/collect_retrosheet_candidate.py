"""Collect the inspected 2025 Retrosheet release into a new private candidate.

This developer CLI never changes production RELEASES, catalogs, models or dates.
The first collection was reviewed independently; both ZIP and CSV pins below
refer to that actual official distribution. No arbitrary URL/year is accepted.
"""
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import os
import secrets
import stat
import sys
import urllib.request
import zipfile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT/'src'))

from baseball_lab.data.lineage import checksum, utc_now, write_json
from baseball_lab.data.protection import open_private, private
from baseball_lab.matchup.outcome_details import PRIMARY, classify
from baseball_lab.r1.provider import OfficialRedirect, TERMS_URL, extract_csv

SEASON = 2025
SOURCE_URL = 'https://www.retrosheet.org/downloads/plays/2025plays.zip'
ARCHIVE_SHA256 = 'ea7f4be3464825b332ed6f8c19e15310858458ea9eddf3e91a954e5b47f69d73'
CSV_SHA256 = '2c58a5ceeae9b653dddc8b4d20fa9b3810bfd3a6d40c29786509c5e060a5f23f'
CREDIT = ('The information used here was obtained free of charge from and is copyrighted by Retrosheet. '
          'Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.')


def download_exact(url, destination, limit):
    """Same TLS, redirect and size controls as the registered-source provider."""
    if url not in (TERMS_URL, SOURCE_URL):
        raise ValueError('검토한 공식 후보 주소만 수집합니다.')
    destination = Path(destination)
    temporary = destination.with_suffix(destination.suffix+'.part')
    if destination.exists() or temporary.exists():
        raise FileExistsError('기존 후보 파일을 덮어쓰지 않습니다.')
    try:
        with urllib.request.build_opener(OfficialRedirect()).open(url, timeout=60) as response, open_private(temporary) as output:
            size = 0
            while block := response.read(1024*1024):
                size += len(block)
                if size > limit:
                    raise ValueError('기존 공식 제공자의 다운로드 크기 한도를 초과했습니다.')
                output.write(block)
        temporary.replace(destination)
        private(destination)
    finally:
        temporary.unlink(missing_ok=True)


def inspect_csv(path):
    """Basic source audit only; no fitted or learned model readiness claim."""
    counts = Counter(); types = Counter(); seen = set(); first = last = None
    required = {'gid', 'pn', 'date', 'gametype', 'pbp', 'pa', 'bip', 'hittype',
                'loc', 'firstf', 'pitches', 'batter', 'pitcher', *PRIMARY}
    with Path(path).open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file); fields = reader.fieldnames or []
        if not required.issubset(fields):
            raise ValueError('필수 원천 열이 없습니다.')
        for row in reader:
            counts['all_csv_rows'] += 1
            if row['gametype'] != 'regular' or row['pbp'] != 'full':
                counts['excluded_non_regular_or_non_full'] += 1
                continue
            counts['regular_full_plays'] += 1
            day = datetime.strptime(row['date'], '%Y%m%d').date()
            if day.year != SEASON:
                raise ValueError('후보 정규시즌에 다른 연도의 날짜가 있습니다.')
            first = day if first is None else min(first, day)
            last = day if last is None else max(last, day)
            if row['pa'] not in ('0', '1'):
                raise ValueError('타석 여부가 올바르지 않습니다.')
            if row['pa'] != '1':
                continue
            identity = (row['gid'], row['pn'])
            if identity in seen:
                raise ValueError('완료 타석 ID가 중복됐습니다.')
            if not row['batter'] or not row['pitcher']:
                raise ValueError('타자·투수 식별자가 없습니다.')
            seen.add(identity)
            classify(row)  # Exactly one of the 14 official PA outcome flags.
            counts['completed_pa'] += 1
            counts['pitch_sequence_present_pa'] += bool(row['pitches'].strip())
            if row['bip'] == '1':
                counts['bip_pa'] += 1
                types[row['hittype'] or 'UNKNOWN'] += 1
                counts['bip_location_missing'] += not row['loc'].strip()
                counts['bip_location_plus_suffix'] += '+' in row['loc']
    if not seen or first is None:
        raise ValueError('후보 정규시즌의 완료 타석이 없습니다.')
    return {'csv_fields': fields, 'date_range': [str(first), str(last)],
            'counts': dict(counts), 'batted_type_counts': dict(types),
            'validation': {'required_fields': True, 'exclusive_primary_pa_flags': True,
                'duplicate_completed_pa_ids': 0, 'all_regular_dates_in_2025': True,
                'turn_sequence_model_audit': False, 'heldout_probability_evaluation': False,
                'counterfactual_strategy_validation': False}}


def new_candidate_directory(root):
    """Never reuse a candidate or follow a link in the fixed storage suffix."""
    parent = Path(root).resolve()
    for component in ('data', 'local', 'retrosheet'):
        parent = parent/component
        if parent.is_symlink():
            raise ValueError('후보 보관 경로에 링크를 사용할 수 없습니다.')
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = parent/('candidate-2025-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3))
    destination.mkdir(mode=0o700, exist_ok=False)
    return destination


def collect(root=REPOSITORY_ROOT):
    if os.name == 'posix':
        os.umask(0o077)
    directory = new_candidate_directory(root)
    manifest = {'schema': 'retrosheet-candidate-acquisition-v1', 'status': 'ACQUIRING_CANDIDATE',
        'started_at': utc_now(), 'season': SEASON, 'url': SOURCE_URL,
        'training_registered': False, 'probability_model_changed': False,
        'pin_status': 'inspected fixed candidate checksums; not a registered production release',
        'raw_redistribution': False, 'credit': CREDIT}
    record = directory/'candidate-manifest.json'
    write_json(record, manifest)
    try:
        notice = directory/'source-notice.html'
        download_exact(TERMS_URL, notice, 2*1024*1024)
        text = notice.read_text(encoding='utf-8', errors='replace')
        if ('free to make any desired use' not in text or 'copyrighted by Retrosheet' not in text
                or SOURCE_URL not in text):
            raise ValueError('공식 고지 또는 명시적인 2025 링크를 확인하지 못했습니다.')
        manifest.update(terms_url=TERMS_URL, terms_sha256=checksum(notice), terms_checked_at=utc_now(),
            usage_basis='Retrosheet official NOTICES permits desired use and requires prominent source copyright credit')
        write_json(record, manifest)
        print('공식 이용 고지·2025 배포 링크 확인', flush=True)
        archive = directory/'2025plays.zip'
        download_exact(SOURCE_URL, archive, 32*1024*1024)
        manifest['archive_sha256'] = checksum(archive)
        if manifest['archive_sha256'] != ARCHIVE_SHA256:
            raise ValueError('공식 후보 ZIP이 검토한 버전과 다릅니다. 자동으로 새 버전을 승인하지 않습니다.')
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            if (len(members) != 1 or members[0].filename != '2025plays.csv'
                    or stat.S_ISLNK(members[0].external_attr >> 16) or members[0].flag_bits & 1):
                raise ValueError('예상과 다른·중복·링크·암호화 압축 멤버입니다.')
            info = members[0]
            manifest['zip_member'] = {'name': info.filename, 'bytes': info.file_size,
                'compressed_bytes': info.compress_size, 'crc32': f'{info.CRC:08x}'}
        parsed = directory/'2025plays.csv'
        # Reuses the 256MiB/200x bound and streaming CRC check, into this new directory only.
        extract_csv(archive, parsed, SEASON)
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip() is not None:
                raise ValueError('후보 ZIP CRC가 다릅니다.')
        manifest.update(zip_crc_verified=True, csv_sha256=checksum(parsed))
        if manifest['csv_sha256'] != CSV_SHA256:
            raise ValueError('추출 CSV가 검토한 후보 버전과 다릅니다.')
        manifest.update(inspect_csv(parsed))
        manifest.update(status='CANDIDATE_ACQUIRED_SCHEMA_CHECKED', completed_at=utc_now(),
                        source_status='REAL_OBSERVED')
        write_json(record, manifest)
        print(f'후보 수집·스키마 검사 완료: {manifest["counts"]["completed_pa"]:,}타석', flush=True)
        print(f'비공개 보관: {directory}', flush=True)
        print('학습 등록·모형 보정·독립 예측 검사는 수행하지 않았습니다.', flush=True)
        return directory, manifest
    except KeyboardInterrupt:
        manifest.update(status='CANDIDATE_ACQUISITION_CANCELLED', stopped_at=utc_now())
        write_json(record, manifest)
        raise
    except Exception as exc:
        manifest.update(status='CANDIDATE_ACQUISITION_FAILED', error_type=type(exc).__name__,
                        error=str(exc), failed_at=utc_now())
        write_json(record, manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description='검토한 공식 2025 Retrosheet 원본을 새 비공개 후보 폴더에 수집합니다.')
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT, help='저장소 루트 (기본: 이 스크립트의 저장소)')
    args = parser.parse_args()
    try:
        collect(args.root)
    except KeyboardInterrupt:
        parser.exit(130, '후보 수집을 중지했습니다. 기존 자료는 유지합니다.\n')
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile) as exc:
        parser.exit(2, f'후보 수집 실패: {exc}\n')


if __name__ == '__main__':
    main()
