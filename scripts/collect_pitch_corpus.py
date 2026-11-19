"""Acquire versioned MLB/KBO/NPB pitch CSVs; normalize only with --normalize."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.pitch_sources import collect

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--leagues',nargs='+',choices=('MLB','KBO','NPB'),default=['MLB','KBO','NPB'])
    p.add_argument('--normalize',action='store_true');a=p.parse_args()
    for league in a.leagues:
        manifest=collect(a.root,league)
        if a.normalize:
            from baseball_lab.data.pitch_corpus import normalize
            print(normalize(a.root,manifest),flush=True)

if __name__=='__main__':main()
