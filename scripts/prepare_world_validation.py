"""Compile exact immutable validation evidence; normal training only reads it."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.experiments.match.pitch_game.validated_world import prepare
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();print(prepare(a.output),flush=True)
