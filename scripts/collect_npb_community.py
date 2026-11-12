#!/usr/bin/env python3
"""Acquire immutable, private NPB community CSV snapshots without crawling NPB.

The publisher's attribution license is evidence of its declaration, not proof
of upstream SPAIA redistribution rights. Downloads remain research candidates.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from baseball_lab.data.lineage import checksum, utc_now, write_json
from baseball_lab.data.protection import open_private, private
from baseball_lab.data.warehouse import local_path

REPOSITORY = 'armstjc/Nippon-Baseball-Data-Repository'
REVISION = '5f9108abdaf7db69d3ca976381cf5f59716e75e8'
API = f'https://api.github.com/repos/{REPOSITORY}'
RAW = f'https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/'
ATTRIBUTION = ('This uses data sourced from the Nippon Baseball Data Repository, '
               'which can be accessed here:\nhttps://github.com/' + REPOSITORY)


def fetch(url, maximum=64 * 1024 * 1024):
    request = urllib.request.Request(url, headers={'User-Agent': 'BaseballLab-community-acquisition/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read(maximum + 1)
        if len(body) > maximum:
            raise ValueError('Source exceeds bounded download size')
        return body


def save(root, folder, name, body):
    path = local_path(root, folder / name)
    current = folder
    for part in Path(name).parts[:-1]:
        current = current / part
        local_path(root, current)
        private(current, directory=True)
    if path.exists():
        raise ValueError('Refusing to replace existing original')
    with open_private(path) as output:
        output.write(body)
    return path


def collect(root, *, pbp_year=2025, workers=4):
    root = Path(root).resolve()
    base = root / 'data/local/community/npb-armstjc'
    # Validate ancestors before any write and retain existing private originals.
    (root / 'data').mkdir(exist_ok=True)
    for ancestor in [root / 'data/local', root / 'data/local/community', base]:
        local_path(root, ancestor)
        if ancestor.is_symlink():
            raise ValueError('Linked storage directory refused')
        private(ancestor, directory=True)
    for previous in sorted(base.glob('*/manifest.json'),reverse=True):
        local_path(root,previous)
        cached=json.loads(previous.read_text())
        years={year for f in cached.get('files',[]) if f.get('kind')=='pbp' for year in f.get('seasons',[])}
        if cached.get('revision')!=REVISION or cached.get('summary',{}).get('failures')!=0 or years!={str(pbp_year)}:continue
        for item in cached['files']+cached['evidence']:
            if checksum(local_path(root,root/item['path']))!=item['sha256']:raise ValueError('보관한 비공식 원본의 지문이 다릅니다.')
        print(json.dumps({'manifest':str(previous.relative_to(root)),'cached':True,**cached['summary']},ensure_ascii=False))
        return cached,previous.parent
    folder = base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    private(folder, directory=True)
    evidence = []
    for name in ['LICENSE', 'README.md', 'get_game_stats.py', 'get_npb_pbp.py', 'get_npb_schedule.py', 'get_npb_standings.py']:
        body = fetch(RAW + name)
        path = save(root, folder, 'evidence/' + name, body)
        evidence.append({'path': str(path.relative_to(root)), 'url': RAW + name, 'sha256': checksum(path)})
    tree_body = fetch(API + f'/git/trees/{REVISION}?recursive=1')
    tree_path = save(root, folder, 'evidence/tree.json', tree_body)
    evidence.append({'path': str(tree_path.relative_to(root)),
                     'url': API + f'/git/trees/{REVISION}?recursive=1', 'sha256': checksum(tree_path)})
    tree = json.loads(tree_body)
    if tree.get('truncated'):
        raise ValueError('Cannot select from truncated repository tree')
    selected = [entry for entry in tree['tree'] if entry['type'] == 'blob'
                and entry['path'].endswith('.csv')
                and (entry['path'].split('/')[0] in ('game_stats', 'schedules', 'standings')
                     or entry['path'].startswith(f'pbp/{pbp_year}-'))]
    if sum(entry.get('size', 0) for entry in selected) > 450 * 1024 * 1024:
        raise ValueError('Selection exceeds bounded batch size')

    def acquire(entry):
        name = entry['path']
        url = RAW + name
        try:
            body = fetch(url)
            if len(body) != entry['size']:
                raise ValueError('Pinned tree and file size disagree')
            if hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest() != entry['sha']:
                raise ValueError('Pinned Git blob and downloaded original disagree')
            path = save(root, folder, 'raw/' + name, body)
            print('NPB 파일 확인 · '+name,flush=True)
            del body
            seasons, dates, games, rows = set(), set(), set(), 0
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                for row in reader:
                    rows += 1
                    year = row.get('season') or row.get('Year')
                    if year: seasons.add(year)
                    if row.get('game_date'): dates.add(row['game_date'][:10])
                    if row.get('game_id'): games.add(row['game_id'])
            return {'path': str(path.relative_to(root)), 'url': url, 'sha256': checksum(path),
                    'git_blob_sha': entry['sha'], 'acquired_at': utc_now(), 'bytes': path.stat().st_size,
                    'rows': rows, 'columns': fields, 'seasons': sorted(seasons),
                    'date_min': min(dates) if dates else None, 'date_max': max(dates) if dates else None,
                    'games': len(games), 'kind': name.split('/')[0], 'status': 'DOWNLOADED'}
        except Exception as error:
            return {'url': url, 'source_path': name, 'status': 'FAILED', 'error_type': type(error).__name__}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        files = list(pool.map(acquire, selected))
    complete = [item for item in files if item['status'] == 'DOWNLOADED']
    manifest = {'schema': 'community-raw-acquisition-v1', 'league': 'NPB',
                'source_namespace': 'armstjc-npb-spaia', 'source_url': 'https://github.com/' + REPOSITORY,
                'revision': REVISION, 'created_at': utc_now(), 'source_status': 'REAL_OBSERVED',
                'rights_status': 'PUBLISHER_DECLARED_UPSTREAM_UNVERIFIED',
                'training_ready': False, 'warehouse_registered': False,
                'license': {'publisher_declaration': 'Custom MIT with additional data attribution clause',
                            'evidence': evidence[:2], 'attribution': ATTRIBUTION,
                            'upstream': 'SPAIA (https://spaia.jp/), identified in README and acquisition code',
                            'upstream_rights_verified': False},
                'evidence': evidence, 'files': files,
                'summary': {'csv_files': len(complete), 'rows': sum(f['rows'] for f in complete),
                            'bytes': sum(f['bytes'] for f in complete), 'failures': len(files) - len(complete)},
                'limitations': ['Publisher-declared license does not establish SPAIA redistribution rights.',
                                'Snapshot coverage is not verified against a complete league schedule.',
                                'Game-stat months can mix exhibition, regular and postseason games.',
                                'PBP rows may include pitch and narrative records; they are not plate appearances.',
                                'Raw candidates are not automatically registered for training or cross-league comparison.',
                                'No official npb.jp crawling or official-source mirror was used.']}
    write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'manifest': str((folder / 'manifest.json').relative_to(root)), **manifest['summary']}, ensure_ascii=False))
    return manifest, folder


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--pbp-year', type=int, default=2025)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--prepare', action='store_true', help='확보 후 명시된 정규시즌 경기만 공통 선수 기록으로 집계')
    args = parser.parse_args()
    manifest, folder = collect(args.root, pbp_year=args.pbp_year, workers=args.workers)
    if manifest['summary']['failures']:raise SystemExit(1)
    if args.prepare:
        from prepare_npb_community import prepare
        print(json.dumps(prepare(args.root,folder/'manifest.json'),ensure_ascii=False))
