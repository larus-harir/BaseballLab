"""Publish only official player ID and display name; all biographies stay private."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from baseball_lab.data.compact import players
from baseball_lab.data.lineage import checksum,write_json
from baseball_lab.data.protection import private


SOURCE_ARCHIVE_SHA256='b389f4616dff02c45676519db6c46b7319e9dbc5be139e5ff31ca5b885f064c1'


def compile_names(root,archive_path):
    root=Path(root).resolve();source=Path(archive_path).read_bytes()
    if len(source)>16*1024*1024:raise ValueError('Name source size limit')
    if hashlib.sha256(source).hexdigest()!=SOURCE_ARCHIVE_SHA256:raise ValueError('Unreviewed official source version')
    with zipfile.ZipFile(io.BytesIO(source)) as z:
        members=[i for i in z.infolist() if i.filename=='biofile0.csv']
        if len(members)!=1 or members[0].file_size>32*1024*1024:raise ValueError('Official name source member invalid')
        raw=z.read(members[0])
    try:text=raw.decode('utf-8-sig');encoding='utf-8-sig'
    except UnicodeDecodeError:text=raw.decode('cp1252');encoding='cp1252'
    wanted={r['source_player_id'] for r in players() if r['league']=='MLB'};names={}
    for row in csv.DictReader(io.StringIO(text,newline='')):
        pid=row['id']
        if pid not in wanted:continue
        name=' '.join(part.strip() for part in (row['usename'],row['lastname']) if part.strip())
        if not name or not re.fullmatch('[a-z0-9-]{8}',pid):raise ValueError('Official ID/name invalid')
        if pid in names and names[pid]!=name:raise ValueError('Conflicting official name for ID')
        names[pid]=name
    missing=sorted(wanted-names.keys())
    if missing:raise ValueError('Unresolved source player IDs: '+str(missing))
    folder=root/'data/local/names'/('retrosheet-'+secrets.token_hex(6));private(folder,directory=True)
    archive=folder/'biodata.zip';archive.write_bytes(source);private(archive)
    provenance={'source_url':'https://www.retrosheet.org/downloads/biodata.zip','source_page':'https://www.retrosheet.org/biofile.htm',
        'archive_sha256':checksum(archive),'member':'biofile0.csv','member_sha256':hashlib.sha256(raw).hexdigest(),'encoding':encoding,
        'retained_fields':['Retrosheet ID','usename + lastname'],'omitted':'Every biographical column and unrelated person',
        'credit':'The information used here was obtained free of charge from and is copyrighted by Retrosheet. https://www.retrosheet.org/notice.txt'}
    write_json(folder/'manifest.json',provenance)
    payload={'schema':'retrosheet-player-display-names-v1','provenance':provenance,'names':dict(sorted(names.items()))}
    out=root/'src/baseball_lab/data/resources/mlb-names-v1.json.gz'
    if out.exists():raise ValueError('Do not overwrite an existing name version')
    out.write_bytes(gzip.compress(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8'),mtime=0))
    print('PLAYERS',len(names),'BYTES',out.stat().st_size,'SHA256',checksum(out))


if __name__=='__main__':compile_names(Path(__file__).resolve().parents[1],sys.argv[1])
