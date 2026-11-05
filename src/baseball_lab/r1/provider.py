"""Official downloadable Retrosheet CSV. Uses published distribution, not page scraping."""
from pathlib import Path
import urllib.request
import zipfile
from urllib.parse import urlparse
from baseball_lab.data.protection import private,open_private

from baseball_lab.data.retrosheet_releases import RELEASES
from baseball_lab.data.lineage import checksum
from .data import normalize, load

TERMS_URL = 'https://www.retrosheet.org/downloads/plays.html'
DATA_URL = 'https://www.retrosheet.org/downloads/plays/2024plays.zip'
# Snapshot actually inspected on 2026-11-04. A corrected upstream release needs
# explicit review/version update, not silently changing the research environment.
ARCHIVE_SHA = 'a3e8c08876ddf70e1ffb0b20486c2873cf4aae19e0acc8002096e9056107615b'


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        parsed=urlparse(newurl)
        if parsed.scheme!='https' or parsed.hostname!='www.retrosheet.org' or parsed.port not in (None,443) or parsed.username:
            raise ValueError('공식 제공자 밖으로 이동하는 다운로드를 거부했습니다.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def extract_csv(archive,destination,year):
    with zipfile.ZipFile(archive) as z:
        members=z.infolist();name=f'{year}plays.csv'
        if len(members)!=1 or members[0].filename!=name:
            raise ValueError('공식 CSV 이외의 압축 경로나 중복 파일을 거부했습니다.')
        info=members[0]
        if info.file_size>256*1024*1024 or info.file_size>max(1,info.compress_size)*200:
            raise ValueError('압축 해제 크기·압축률 한도를 초과했습니다.')
        temporary=Path(destination).with_suffix('.csv.part')
        try:
            with z.open(info) as src,open_private(temporary) as out:
                private(temporary);size=0
                while block:=src.read(1024*1024):
                    size+=len(block)
                    if size>256*1024*1024:raise ValueError('압축 해제 크기 한도 초과')
                    out.write(block)
            temporary.replace(destination)
        finally:temporary.unlink(missing_ok=True)


def download(url, destination, limit):
    allowed={TERMS_URL,*(r['url'] for r in RELEASES.values())}
    if url not in allowed:raise ValueError('등록된 공식 HTTPS 주소만 다운로드할 수 있습니다.')
    destination = Path(destination)
    temporary = destination.with_suffix(destination.suffix+'.part')
    try:
        with urllib.request.build_opener(OfficialRedirect()).open(url, timeout=60) as response, open_private(temporary) as out:
            private(temporary)
            size = 0
            while block := response.read(1024*1024):
                size += len(block)
                if size > limit:raise ValueError('공식 배포 파일의 크기 한도를 초과했습니다.')
                out.write(block)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def acquire(root, year=2024):
    destination = Path(root).resolve()/f'official-{year}'
    if year not in RELEASES:
        raise ValueError('개별 확인한 2023·2024년 공식 배포만 지원합니다.')
    release=RELEASES[year]
    if (destination/'dataset.json').exists():
        print('단계 1 · 보관한 실제 Retrosheet 기록의 체크섬을 확인합니다.', flush=True)
        data=load(destination/'dataset.json')
        if (data['manifest'].get('source_version')!=release['sha256']
                or checksum(destination/f'{year}plays.zip')!=release['sha256']):
            raise ValueError('보관 자료가 등록된 공식 배포 버전과 다릅니다.')
        return data
    print(f'단계 1 · Retrosheet 공식 배포에서 {year}년 실제 플레이 기록을 준비합니다.', flush=True)
    private(destination,directory=True)
    terms = destination/'source-notice.html'
    download(TERMS_URL, terms, 2*1024*1024)
    notice = terms.read_text(encoding='utf-8', errors='replace')
    if 'free to make any desired use' not in notice or 'copyrighted by Retrosheet' not in notice:
        raise ValueError('공식 이용 고지가 변경됐거나 확인되지 않습니다. 제공 조건을 다시 검토해야 합니다.')
    archive = destination/f'{year}plays.zip'
    if not archive.exists():download(release['url'], archive, 32*1024*1024)
    if checksum(archive) != release['sha256']:
        raise ValueError('공식 배포 버전의 체크섬이 변경됐습니다. 수정 자료인지 확인하기 전에는 학습하지 않습니다.')
    csv_path = destination/f'{year}plays.csv'
    extract_csv(archive,csv_path,year)
    return normalize(csv_path, destination, {
        'provider': 'Retrosheet official parsed play-by-play CSV',
        'source_url': release['url'], 'source_version': release['sha256'], 'season':year,
        'usage_basis': 'Official plays.html NOTICES verified: recipients free to make any desired use; prominent required copyright credit retained.',
        'terms_path': str(terms), 'terms_url': TERMS_URL, 'terms_sha256': checksum(terms),
        'raw_files': [{'path': str(archive), 'sha256': checksum(archive)},
                      {'path': str(csv_path), 'sha256': checksum(csv_path)}]}, official=True,
                     skip_empty_no_play=release.get('skip_empty_no_play',False))
