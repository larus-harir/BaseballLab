"""Compile whitelisted public aggregates and pinned source metadata; no originals."""
import csv
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from baseball_lab.data.lineage import checksum,content_hash
from baseball_lab.data.training_window import sources
from baseball_lab.matchup.shared import catalog
from baseball_lab.experiments.match.team_win.mixed import npb_before
ROOT=Path(__file__).resolve().parents[1]


def compile_sources(root,destination):
    destination.mkdir(parents=True,exist_ok=True)
    data=catalog(root)
    keys=('schema','league','season','role','source_namespace','source_player_id','row_kind','team','entity_id','source_sha256','counts','missing_reasons','units','events','eligibility','limitations','granularity','provenance_status','rights_status','publisher_license')
    rows=[]
    for p in data['profiles'].values():
        if p['provenance_status']!='REAL_OBSERVED' and p['source_namespace']!='supplied-kbo-assignment':raise ValueError('Non-observed compilation refused')
        row={k:p[k] for k in keys if k in p}
        row['source_fields']={k:v for k,v in p.get('source_fields',{}).items() if k in ('Name','teams','team_label')}
        rows.append(row)
    payload={'schema':'compact-player-aggregates-v1','source_dataset_id':data['dataset_id'],'rows':rows}
    body=gzip.compress(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8'),mtime=0)
    (destination/'players.json.gz').write_bytes(body)
    periods={}
    for year,m in sorted(sources(root).items()):
        games={};csvfile=next(f for f in m['files'] if f['path'].endswith('.csv'))
        zipfile=next(f for f in m['files'] if f['path'].endswith('.zip'))
        path=root/csvfile['path']
        if checksum(path)!=csvfile['sha256'] or checksum(root/zipfile['path'])!=zipfile['sha256']:raise ValueError('Source checksum mismatch')
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['gametype']=='regular' and r['pbp']=='full':games[r['gid']]=max(games.get(r['gid'],''),r['date'])
        days=sorted({v[:4]+'-'+v[4:6]+'-'+v[6:] for v in games.values()})
        periods[str(year)]={'dates':days,'start':days[0],'end':days[-1],'source_url':m['source_url'],'zip_sha256':zipfile['sha256'],'csv_sha256':csvfile['sha256'],'credit':m['credit']}
        print('MLB',year,'index verified',flush=True)
    npb=npb_before(root,'9999-12-31',by_day=True)
    index={'schema':'compact-source-index-v1','players_sha256':checksum(destination/'players.json.gz'),'players_rows':len(rows),'source_dataset_id':data['dataset_id'],'mlb':periods,'npb':npb,
      'licenses':{'retrosheet':'https://www.retrosheet.org/downloads/plays.html','kbo':'CC BY-NC-SA 4.0; https://www.kaggle.com/datasets/netsong/kbo-player-stats-19822025, Kaggle version 7','npb':npb['attribution']},
      'scope':'Derived matchup counts and dated NPB PA marginal totals only. No raw games, biographies, trained weights or invented missing values. Upstream NPB rights/accuracy are not independently verified.'}
    (destination/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('INDEX SHA256',checksum(destination/'index.json'),'PLAYERS BYTES',len(body),'ROWS',len(rows),flush=True)


if __name__=='__main__':compile_sources(ROOT,ROOT/'src/baseball_lab/data/resources')
