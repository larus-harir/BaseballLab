"""Build a private multi-league collection dataset, preserving every season."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.warehouse import build

def main():
    p=argparse.ArgumentParser(description='수집 자료를 리그별 전체/최근 N시즌/기간으로 표준화합니다. 원본·기존 모형은 변경하지 않습니다.')
    p.add_argument('--leagues',nargs='+',choices=('MLB','KBO','NPB'))
    p.add_argument('--start-season',type=int);p.add_argument('--end-season',type=int)
    p.add_argument('--last-seasons',type=int);p.add_argument('--root',type=Path,default=ROOT)
    a=p.parse_args()
    try:
        manifest,folder=build(a.root,leagues=a.leagues,start=a.start_season,end=a.end_season,last_seasons=a.last_seasons)
        print(json.dumps({'dataset_id':manifest['dataset_id'],'rows':manifest['rows'],'coverage':manifest['coverage'],'output':str(folder)},ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError) as exc:p.exit(2,str(exc)+'\n')

if __name__=='__main__':main()
