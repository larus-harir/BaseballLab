"""Compile recorded contact areas from existing verified private pitch releases."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.batting_directions import compile_directions
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 print(json.dumps(compile_directions(a.root,a.output),ensure_ascii=False),flush=True)
