"""Evidence states are separate from model/run status; never infer reality from a path."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import hashlib
import json
import os
from .protection import private


class SourceStatus(str, Enum):
    REAL_OBSERVED = 'REAL_OBSERVED'
    EMPIRICALLY_ESTIMATED = 'EMPIRICALLY_ESTIMATED'
    MODEL_SIMULATED = 'MODEL_SIMULATED'
    UNVERIFIED_ASSUMPTION = 'UNVERIFIED_ASSUMPTION'
    MOCK_TEST_ONLY = 'MOCK_TEST_ONLY'


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def checksum(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as file:
        json.dump(payload,file,ensure_ascii=False,indent=2,allow_nan=False)
        file.write('\n')
    temporary.replace(path)
    private(path)


@dataclass(frozen=True)
class RawSource:
    source_name: str
    source_url: str
    path: str
    acquired_at: str
    raw_file_checksum: str
    source_status: str
    licensing_notes: str
    acquisition_method: str

    def verify(self):
        path = Path(self.path)
        if not path.is_file() or checksum(path) != self.raw_file_checksum:
            raise ValueError(f'원본 파일 누락 또는 해시 불일치: {path}')
        if self.source_status not in {status.value for status in SourceStatus}:
            raise ValueError('알 수 없는 데이터 상태')
        return path

    def to_dict(self):
        return asdict(self)
