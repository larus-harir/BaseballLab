"""Register observed regular-season player totals from pinned community CSVs."""
import csv,json,sys,argparse
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from baseball_lab.data.community import integer,outs,register
from baseball_lab.data.warehouse import local_path
from baseball_lab.data.lineage import checksum,content_hash


def prepare(root,manifest):
    root=Path(root).resolve();manifest=local_path(root,Path(manifest).resolve());meta=json.loads(manifest.read_text(encoding='utf-8'));games={};counts=Counter()
    files=meta['files']
    for item in files:
        if item.get('kind') not in ('pbp','game_stats'):continue
        path=local_path(root,root/item['path'])
        if checksum(path)!=item['sha256']:raise ValueError('NPB 원본 CSV 지문이 다릅니다.')
        if item['kind']!='pbp':continue
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                label=(r['game_type_id'],r['game_type_name']);old=games.get(r['game_id'])
                if old and old!=label:raise ValueError('경기 종류가 서로 모순됩니다.')
                games[r['game_id']]=label
    regular={'1':'セ・リーグ公式戦','2':'パ・リーグ公式戦','26':'セ・パ交流戦'}
    allowed={g for g,(kind,label) in games.items() if regular.get(kind)==label}
    if not allowed:raise ValueError('정규시즌으로 명시된 경기 종류가 없어 시즌 집계를 만들지 않았습니다.')
    groups={};seen=set();used_games=set();source_hashes=[]
    for item in files:
        if item.get('kind')!='game_stats':continue
        path=local_path(root,root/item['path']);source_hashes.append(item['sha256'])
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['game_id'] not in allowed:
                    counts['unknown_game_type' if r['game_id'] not in games else 'non_regular']+=1;continue
                identity=(r['game_id'],r['player_id'],r['team_id'])
                if identity in seen:raise ValueError('선수·경기·팀 행이 중복됐습니다.')
                seen.add(identity);used_games.add(r['game_id']);counts['regular_player_games']+=1
                for role,prefix,den in (('batter','batting_','PA'),('pitcher','pitching_','BF')):
                    if r.get(prefix+den,'')=='':continue
                    key=(integer(r['season']),role,r['player_id'])
                    group=groups.setdefault(key,{'names':set(),'teams':set(),'rows':[]})
                    group['names'].add(r['player_name_jap']);group['teams'].add(r['team_id'])
                    fields=('G','PA','AB','H','2B','3B','HR','BB','HBP','SO','R','RBI','SB','CS','SH','SF','ER','W','L','SV','CG','SHO','BK','IBB')
                    c={k:integer(r[prefix+k]) for k in fields if prefix+k in r}
                    if role=='pitcher':c['TBF']=integer(r[prefix+'BF'])
                    if role=='pitcher' and r.get(prefix+'IP_str'):c['IP_OUTS']=outs(r[prefix+'IP_str'])
                    group['rows'].append(c)
    result=[];sha=content_hash(sorted(source_hashes)+[item['sha256'] for item in files if item.get('kind')=='pbp'])
    for (season,role,pid),group in groups.items():
        if len(group['names'])!=1:raise ValueError('제공자 선수 ID에 다른 이름이 연결됐습니다.')
        keys=set().union(*(r.keys() for r in group['rows']))
        totals={k:sum(r[k] for r in group['rows']) if all(r.get(k) is not None for r in group['rows']) else None for k in keys}
        result.append({'league':'NPB','season':season,'role':role,'granularity':'player_season','row_kind':'season_total',
            'source_namespace':'armstjc-npb-spaia','source_player_id':pid,'source_sha256':sha,'counts':totals,
            'source_fields':{'Name':next(iter(group['names'])),'teams':sorted(group['teams']),'observed_games':len(group['rows']),
                'coverage':'only observed games with explicit regular-season type; not guaranteed complete official season'}})
    m=register(root,result,{'league':'NPB','source_namespace':'armstjc-npb-spaia','source_url':meta['source_url'],
        'publisher_license':meta['license']['publisher_declaration'],'source_revision':meta['revision'],
        'raw_manifest':str(manifest.relative_to(root)),'registered_games':len(used_games),
        'exclusions':dict(counts),'full_season_completeness_verified':False})
    return {'rows':m['row_count'],'registered_games':len(used_games),'coverage':sorted({r['season'] for r in result}),'filter_counts':dict(counts)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);a=p.parse_args();print(json.dumps(prepare(ROOT,a.manifest),ensure_ascii=False,indent=2))
