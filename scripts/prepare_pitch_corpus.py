"""Compile source-derived cohort counts; preserve previous databases and assets."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.pitch_corpus import build_counts

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();chosen={}
    for file in sorted((a.root/'data/local/pitch-corpus').glob('*/manifest.json')):
        m=json.loads(file.read_text(encoding='utf-8'))
        if m.get('status')!='NORMALIZED':continue
        old=chosen.get(m['league'])
        if not old or m['created_at']>old[0]:chosen[m['league']]=(m['created_at'],file)
    if set(chosen)!={'MLB','KBO','NPB'}:raise ValueError('3개 리그의 원본 수집·정규화를 먼저 실행하세요.')
    print(json.dumps(build_counts(a.root,[v[1] for v in chosen.values()],a.output),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
