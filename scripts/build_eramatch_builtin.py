"""Compile only matchup fields from the reviewed assignment into package data.

Developer release step, not an end-user upload requirement. Never executes the
supplied program or includes the CSVs/report themselves in the application.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.matchup.catalog import import_assignment,LEGACY_FILES,LEGACY_SHA,identity
from baseball_lab.data.lineage import content_hash
from baseball_lab.experiments.eramatch.builtin import validate_public_fields,BUNDLE_SCHEMA,BUNDLE_NAME


def compile_bundle(archive,output,report=None):
    content=Path(archive).read_bytes()
    if hashlib.sha256(content).hexdigest()!=LEGACY_SHA:raise ValueError('검토한 과제 ZIP 버전이 아닙니다.')
    with tempfile.TemporaryDirectory(prefix='eramatch-compile-') as directory:
        data=import_assignment(Path(directory),content)
    validate_public_fields(data)
    # Timestamp is not a statistical input or an asserted new acquisition.
    data['source']['acquired_at']=None
    assert content_hash(identity(data))==data['dataset_id']
    with ZipFile(archive) as z:
        inputs={Path(name).name:hashlib.sha256(z.read(name)).hexdigest() for name in LEGACY_FILES}
    provenance={'archive_sha256':LEGACY_SHA,'input_sha256':inputs,
                'retained':'player ID/name, league/season/team, matchup counts and reproducible model baselines',
                'excluded_fields':['Birthdate','School','Draft','Handedness','Age','Pos.'],
                'original_code_included':False,'original_csv_included':False,'original_report_included':False}
    if report:provenance['reference_report_sha256']=hashlib.sha256(Path(report).read_bytes()).hexdigest()
    payload={'schema':BUNDLE_SCHEMA,'catalog':data,'provenance':provenance}
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    compressed=gzip.compress(raw,compresslevel=9,mtime=0)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(compressed)
    manifest={'schema':BUNDLE_SCHEMA,'file':BUNDLE_NAME,'sha256':hashlib.sha256(compressed).hexdigest(),
              'dataset_id':data['dataset_id'],'profile_count':len(data['profiles']),
              'seasons':sorted({p['season'] for p in data['profiles'].values()}),'provenance':provenance}
    output.with_name('manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'src/baseball_lab/experiments/eramatch/resources'/BUNDLE_NAME)
    args=parser.parse_args();manifest=compile_bundle(args.archive,args.output,args.report)
    print(json.dumps({k:v for k,v in manifest.items() if k!='provenance'},ensure_ascii=False,indent=2))
