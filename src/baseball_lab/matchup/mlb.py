"""Official observed PA catalog and chronological predictive comparison."""
from collections import defaultdict
from datetime import datetime
import csv
import io
import math
from pathlib import Path
from zipfile import ZipFile
import urllib.request

from baseball_lab.data.lineage import checksum,content_hash,utc_now
from baseball_lab.data.protection import private,open_private
from baseball_lab.r1.provider import acquire,OfficialRedirect
from .catalog import save_catalog,source_directory
from .models import EVENTS,distribution,stabilize,generalized_log5

ROSTER_URL='https://www.retrosheet.org/events/2024eve.zip'
ROSTER_SHA='5dfd9ed678c9c619f6a216322922c99234c067d0ec15b12790546f620ced2fa4'
FLAGS=('k','walk','hbp','single','double','triple','hr')


def rosters(directory):
    path=directory/'2024eve.zip'
    if not path.exists():
        temp=path.with_suffix('.part')
        try:
            with urllib.request.build_opener(OfficialRedirect()).open(ROSTER_URL,timeout=45) as response,open_private(temp) as file:
                n=0
                while chunk:=response.read(1024*1024):
                    n+=len(chunk)
                    if n>32*1024*1024:raise ValueError('공식 이름 자료의 다운로드 한도 초과')
                    file.write(chunk)
            temp.replace(path)
        finally:temp.unlink(missing_ok=True)
    if checksum(path)!=ROSTER_SHA:raise ValueError('공식 선수 이름 자료의 버전이 달라졌습니다.')
    names={}
    with ZipFile(path) as z:
        for info in z.infolist():
            if not info.filename.upper().endswith('.ROS'):continue
            if info.file_size>1024*1024:raise ValueError('이름 자료 파일 한도 초과')
            for row in csv.reader(io.StringIO(z.read(info).decode('utf-8-sig'))):
                if len(row)<3:raise ValueError('이름 자료의 열이 부족합니다.')
                names[row[0]]=row[2]+' '+row[1]
    return names


def observed_rows(path):
    rows=[];seen=set()
    with Path(path).open(encoding='utf-8-sig',newline='') as file:
        for raw in csv.DictReader(file):
            if raw['gametype']!='regular' or raw['pbp']!='full' or raw['pa']!='1':continue
            identity=(raw['gid'],raw['pn'])
            if identity in seen:raise ValueError('공식 타석 ID 중복')
            seen.add(identity)
            flags=[int(raw[f]) for f in FLAGS]
            if any(f not in (0,1) for f in flags) or sum(flags)>1:raise ValueError('배타적 타석 사건이 중복됐습니다.')
            event=EVENTS[flags.index(1)] if sum(flags)==1 else 'other'
            # Match order: FLAGS and EVENTS start K, BB, HBP, 1B, 2B, 3B, HR.
            actual_date=raw['date']
            if len(actual_date)!=8:raise ValueError('실제 플레이 날짜가 필요합니다.')
            datetime.strptime(actual_date,'%Y%m%d')
            rows.append({'id':raw['gid']+':'+raw['pn'],'game':raw['gid'],'date':actual_date,
                         'batter':raw['batter'],'pitcher':raw['pitcher'],'event':event,
                         'batteam':raw['batteam'],'pitteam':raw['pitteam'],
                         'ab':int(raw['ab']),'sf':int(raw['sf']),'sh':int(raw['sh'])})
    if not rows:raise ValueError('완료된 실제 타석 기록이 없습니다.')
    return rows


def tally(rows,role):
    result={}
    for row in rows:
        pid=row[role]
        if pid not in result:result[pid]={e:0 for e in EVENTS}
        result[pid][row['event']]+=1
    return result


def evaluate(rows,batters,pitchers,league,*,strength,kind):
    cache={};loss=brier=0.;bins=[{'n':0,'predicted_sum':0.,'observed_sum':0} for _ in range(10)];cold=0
    for row in rows:
        pair=(row['batter'],row['pitcher'])
        if pair not in cache:
            b=stabilize(batters.get(pair[0],{e:0 for e in EVENTS}),league,strength)
            p=stabilize(pitchers.get(pair[1],{e:0 for e in EVENTS}),league,strength)
            cache[pair]=generalized_log5(b,p,league)[0] if kind=='log5' else b if kind=='batter' else league
        q=cache[pair];event=row['event'];prob=q[event]
        if prob<=0:return {'n':len(rows),'log_loss':None,'reason':'보류 표본의 실제 사건에 0 확률을 부여했습니다.'}
        loss-=math.log(prob);brier+=sum((q[e]-(e==event))**2 for e in EVENTS)
        # Calibration of hit probability, with its exact event definition.
        hit=sum(q[e] for e in ('single','double','triple','home_run'));bucket=bins[min(9,int(hit*10))]
        bucket['n']+=1;bucket['predicted_sum']+=hit;bucket['observed_sum']+=event in ('single','double','triple','home_run')
        cold+=row['batter'] not in batters or row['pitcher'] not in pitchers
    return {'n':len(rows),'log_loss':loss/len(rows),'brier':brier/len(rows),'hit_calibration':bins,'cold_start_n':cold}


def validate(rows):
    # A suspended game can resume months after its game-ID date. Keep its
    # entire game in the period where all its observed PA are available.
    complete={}
    for r in rows:complete[r['game']]=max(complete.get(r['game'],''),r['date'])
    parts={'fit':[r for r in rows if complete[r['game']]<'20240715'],
           'validation':[r for r in rows if '20240715'<=complete[r['game']]<'20240825'],
           'test':[r for r in rows if complete[r['game']]>='20240825']}
    if any(not r for r in parts.values()):raise ValueError('독립적인 세 경기 기간이 필요합니다.')
    games=[{r['game'] for r in part} for part in parts.values()]
    if any(games[i]&games[j] for i in range(3) for j in range(i+1,3)):raise ValueError('경기 분리 누수')
    b,p=tally(parts['fit'],'batter'),tally(parts['fit'],'pitcher')
    league=distribution({e:sum(c[e] for c in b.values()) for e in EVENTS})
    candidates=[]
    for strength in (25,100,300,1000):
        metric=evaluate(parts['validation'],b,p,league,strength=strength,kind='log5')
        candidates.append({'strength':strength,**metric})
    chosen=min((c for c in candidates if c['log_loss'] is not None),key=lambda c:c['log_loss'])
    comparison={kind:{stage:evaluate(part,b,p,league,strength=chosen['strength'],kind=kind)
                      for stage,part in parts.items() if stage!='fit'} for kind in ('league','batter','log5')}
    return {'method':'Chronological held-out PA prediction; all profiles and priors use fit only; suspended games grouped by last actual PA date, never game-ID date.',
            'split':{k:{'n':len(v),'games':len({r['game'] for r in v}),'record_hash':content_hash([r['id'] for r in v]),
                        'dates':[min(complete[r['game']] for r in v),max(complete[r['game']] for r in v)]} for k,v in parts.items()},
            'suspended_game_handling':{'policy':'entire game assigned by last actual observed PA date',
                'cross_date_games':sum(len({r['date'] for r in rows if r['game']==g})>1 for g in {r['game'] for r in rows if r['date']!=r['game'][3:11]})},
            'selected_strength':chosen['strength'],'validation_candidates':candidates,'comparison':comparison,
            'research_ready':comparison['log5']['test']['log_loss'] is not None and comparison['log5']['test']['log_loss']<=comparison['league']['test']['log_loss'],
            'scope':'Predictive check in MLB 2024 only. No causal matchup, KBO, cross-era or player ability guarantee. Full-season exploratory profiles are distinct from fit-only evaluation profiles.'}


def prepare(root):
    root=Path(root);directory=source_directory(root,'mlb-2024');private(directory,directory=True)
    real=acquire(root/'data/local/retrosheet',year=2024);manifest=real['manifest'];del real
    names=rosters(directory);rows=observed_rows(manifest['parsed_csv_path']);validation=validate(rows)
    profiles={};counts_by_role={role:tally(rows,role) for role in ('batter','pitcher')}
    league_counts={e:sum(c[e] for c in counts_by_role['batter'].values()) for e in EVENTS};league=distribution(league_counts)
    for role,groups in counts_by_role.items():
        aux=defaultdict(lambda:{'AB':0,'SF':0,'SH':0,'teams':set()})
        for r in rows:
            c=aux[r[role]];c['AB']+=r['ab'];c['SF']+=r['sf'];c['SH']+=r['sh'];c['teams'].add(r['batteam' if role=='batter' else 'pitteam'])
        for pid,events in groups.items():
            info=aux[pid];n=sum(events.values());hits=sum(events[e] for e in ('single','double','triple','home_run'))
            counts={'PA' if role=='batter' else 'TBF':n,'AB':info['AB'],'SF':info['SF'],'SH':info['SH'],'H':hits,'SO':events['strikeout'],'BB':events['walk'],'HBP':events['hbp'],'HR':events['home_run'],'2B':events['double'],'3B':events['triple']}
            key=f'MLB:{role}:{pid}:2024'
            profiles[key]={'id':key,'player_id':pid,'name':names.get(pid,pid),'season':2024,'league':'MLB','role':role,
                           'teams':sorted(info['teams']),'counts':counts,'events':events,'league_rates':league,'issues':[],
                           'legacy_eligible':False,'normalized_eligible':True,'status':'REAL_OBSERVED'}
    archive=Path(manifest['raw_files'][0]['path']);local=directory/'2024plays.zip'
    if not local.exists():shutil_copy(archive,local)
    elif checksum(local)!=checksum(archive):raise ValueError('공식 카탈로그 원본 버전 충돌')
    source={'id':'mlb-2024','label':'Retrosheet · MLB 2024 정규시즌','status':'REAL_OBSERVED','league':'MLB',
            'source_url':manifest['source_url'],'license':manifest['credit'],'acquired_at':utc_now(),
            'files':[{'name':p.name,'sha256':checksum(p)} for p in (local,directory/'2024eve.zip')],
            'original_dataset_id':manifest['dataset_id'],'name_source_url':ROSTER_URL}
    return save_catalog(directory,{'schema':'player-season-catalog-v1','source':source,'profiles':profiles,
            'league_counts':{'2024':league_counts},'neutral_rates':league,'validation':validation,'default_model':'normalized' if validation['research_ready'] else 'league',
            'models':{'normalized':{'status':'PREDICTIVE_CHECKED' if validation['research_ready'] else 'EXPLORATORY_ONLY','strength':validation['selected_strength']},'league':{'status':'EMPIRICAL_BASELINE'}}})


def shutil_copy(source,target):
    with Path(source).open('rb') as src,open_private(target) as out:
        while block:=src.read(1024*1024):out.write(block)
