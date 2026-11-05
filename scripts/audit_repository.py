"""Bounded-content disclosure: report names/counts, never matched credential values."""
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PATTERNS=[rb'gh[pousr]_[A-Za-z0-9]{30,}',rb'github_pat_[A-Za-z0-9_]{40,}',
          rb'AKIA[A-Z0-9]{16}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def audit():
    tracked=[p for p in git('ls-files','-z').decode().split('\0') if p]
    private=[p for p in tracked if p.startswith(('data/local/','outputs/','models/'))
             or p.endswith(('.zip','.pem','.key','.p12')) or Path(p).name=='.env']
    hits=[];count=0
    for line in git('rev-list','--objects','--all').splitlines():
        parts=line.split(b' ',1)
        if len(parts)!=2:continue
        oid,path=parts
        if git('cat-file','-t',oid.decode()).strip()!=b'blob':continue
        count+=1;data=git('cat-file','blob',oid.decode())
        if any(re.search(pattern,data) for pattern in PATTERNS):hits.append({'path':path.decode(errors='replace'),'object':oid.decode()})
    for path in tracked:
        p=ROOT/path
        if p.is_file() and any(re.search(pattern,p.read_bytes()) for pattern in PATTERNS):hits.append({'path':path,'object':'working-tree'})
    return {'tracked_files':len(tracked),'tracked_private_artifact_paths':private,
            'historical_blobs_scanned':count,'recognized_key_pattern_hits':hits,
            'scope':'Known token/private-key patterns only; no proof of absence of all secrets or personal data.'}


if __name__=='__main__':
    report=audit();print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(bool(report['tracked_private_artifact_paths'] or report['recognized_key_pattern_hits']))
