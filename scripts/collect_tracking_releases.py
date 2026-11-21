"""Acquire fixed public supplements without asking users to find/upload files."""
import sys,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.tracking_sources import collect,RELEASES
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',choices=RELEASES,required=True);a=p.parse_args();print(collect(ROOT,a.source),flush=True)
