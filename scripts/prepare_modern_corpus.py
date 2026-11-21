"""Prepare the one modern-baseball study, preserving all prior assets."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--collect',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
 if a.collect:
  from baseball_lab.data.modern_sources import collect,collect_history
  print(collect(ROOT),flush=True);print(collect_history(ROOT),flush=True)
 if a.output:
  from baseball_lab.data.modern_corpus import prepare
  print(json.dumps(prepare(ROOT,a.output),ensure_ascii=False),flush=True)
