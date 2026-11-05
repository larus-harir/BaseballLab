"""Local protection helpers. Encryption and Windows ACL isolation are not implied."""
import os
from pathlib import Path
import re


def private(path, *, directory=False):
    path=Path(path)
    if directory:path.mkdir(parents=True,exist_ok=True)
    if os.name=='posix':path.chmod(0o700 if directory else 0o600)
    return path


def public_text(value):
    text=str(value)
    text=re.sub(r'(https?://)[^/\s]+@',r'\1[비공개]@',text)
    text=re.sub(r'(?i)\b(bearer)\s+[^\s,;]+',r'\1 [비공개]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|token|secret|password|authorization)\s*[=:]\s*)[^\s,;]+',r'\1[비공개]',text)
    text=re.sub(r'(?<![:\w])(?:[A-Za-z]:[\\/]|/(?:workspace|tmp|home|Users|private)/)[^\s\"\'<>]+','[로컬 경로]',text)
    return text


def public_view(value):
    """Derived display only: private lineage stays unchanged on disk."""
    if isinstance(value,dict):
        return {k:public_view(v) for k,v in value.items() if k not in (
            'path','parsed_csv_path','terms_path','raw_files','usage_note','licensing_notes',
            'authorization_reference','token','password','secret','api_key')}
    if isinstance(value,(list,tuple)):return [public_view(v) for v in value]
    return public_text(value) if isinstance(value,str) else value


def open_private(path):
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0),0o600)
    return os.fdopen(descriptor,'wb')
