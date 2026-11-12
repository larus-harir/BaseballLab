"""Download fixed public community CSV releases; keep originals private."""
import sys,argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.community import acquire_kbo,KBO_SOURCES

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--source',choices=KBO_SOURCES,action='append');a=p.parse_args()
    for ref in a.source or KBO_SOURCES:
        m=acquire_kbo(a.root,ref)
        print(json.dumps({'source':ref,'version':m['version'],'license':m['publisher_license'],'raw_rows':m['raw_rows'],
            'files':[{k:v for k,v in f.items() if k in ('path','rows','seasons','quality_issues')} for f in m['files']],
            'registered_rows':m.get('registered_rows',0)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
