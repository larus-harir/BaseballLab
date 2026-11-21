import argparse,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.tracking_corpus import prepare
from baseball_lab.data.tracking_sources import definitions
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();definitions(ROOT);print(json.dumps(prepare(ROOT,a.output),ensure_ascii=False),flush=True)
