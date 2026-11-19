"""Use all verified Retrosheet years, without inventing missing tracking fields.

Detailed Gameday cohorts win for overlapping pitch observations. Retrosheet
owns MLB runner transitions, so overlapping providers are not double-counted.
Earlier observed running plays can inform later cohorts, never future plays.
"""
import csv,re
from collections import Counter,defaultdict
from pathlib import Path
from .lineage import checksum,content_hash
from .training_window import sources
from .warehouse import local_path


def datestr(text):return text[:4]+'-'+text[4:6]+'-'+text[6:8]


def movement(r):
    outs=int(r['outs_pre']);delta=int(r['outs_post'])-outs
    bases=sum(1<<(i-1) for i in (1,2,3) if r['br'+str(i)+'_pre'])
    end=sum(1<<(i-1) for i in (1,2,3) if r['br'+str(i)+'_post']) if outs+delta<3 else 0
    runs=int(r['runs']);participants=bases.bit_count()+(r['pa']=='1')
    if not 0<=outs<=2 or not 0<=delta<=3-outs:return None
    if outs+delta<3 and delta+end.bit_count()+runs!=participants:return None
    if outs+delta==3 and delta+runs>participants:return None
    return outs,bases,delta,end,runs


def running(r,date):
    if r['pa']!='0' or not re.search(r'>[BC]$',r['pitches']):return None
    event=r['event']
    pieces=event.split(';')
    if not all(re.fullmatch(r'(SB[234H]|CS[234H]\([1-9]+\))',v) for v in pieces):return None
    count=r['count'].zfill(2)
    if not re.fullmatch('[0-2][01]',count):return None
    state=movement(r)
    if state is None:return None
    outs,bases,delta,end,runs=state
    targets=tuple(sorted({4 if v[2]=='H' else int(v[2]) for v in pieces}))
    if any(not bases&(1<<(target-2)) for target in targets):return None
    return {'date':date,'outs':outs,'bases':bases,'balls':int(count[0]),'strikes':int(count[1]),
        'action':'steal_'+'_'.join(map(str,targets)),
        'outcome':('ball' if r['pitches'][-1]=='B' else 'strike',delta,end,runs)}


def enrich(root,value):
    from baseball_lab.experiments.match.pitch_game.research import checked_sequence
    root=Path(root).resolve();available=sources(root);all_running=[];lineage=[];native={}
    for year,source in sorted(available.items()):
        entry=next((f for f in source['files'] if f['path'].endswith('.csv')),None)
        if not entry:continue
        path=local_path(root,root/entry['path'])
        if checksum(path)!=entry['sha256']:raise ValueError('기존 MLB 원본 지문 불일치')
        calendar={}
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['gametype']=='regular' and r['pbp']=='full':calendar[r['gid']]=max(calendar.get(r['gid'],''),r['date'])
        days=sorted({datestr(d) for d in calendar.values()})
        if len(days)<3:continue
        a=max(1,int(len(days)*.6));b=min(len(days)-1,max(2,int(len(days)*.8)))
        richer=next((c for c in value['cohorts'].values() if c['league']=='MLB' and c['season']==year),None)
        split=richer['split'] if richer else {'fit':[days[0],days[a-1]],'validation':[days[a],days[b-1]],'test':[days[b],days[-1]]}
        counts={p:defaultdict(Counter) for p in split};moves={p:defaultdict(Counter) for p in split};players=Counter();repertoires=defaultdict(Counter);pitch_rows=0
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['gametype']!='regular' or r['pbp']!='full':continue
                day=datestr(calendar[r['gid']]);phase=next((p for p,(lo,hi) in split.items() if lo<=day<=hi),None)
                if not phase:continue
                run=running(r,day)
                if run:all_running.append(run)
                if r['pa']!='1':continue
                event=('single' if r['single']=='1' else 'double' if r['double']=='1' else 'triple' if r['triple']=='1' else
                       'home_run' if r['hr']=='1' else 'strikeout' if r['k']=='1' else 'walk' if r['walk']=='1' else 'hbp' if r['hbp']=='1' else 'out')
                m=movement(r)
                if m and int(r['inning'])<=8:
                    outs,bases,delta,end,runs=m;moves[phase][outs,bases,event,r['bunt']=='1'][delta,end,runs]+=1
                if '.' in r['pitches']:continue
                seq,reason=checked_sequence({'pitches':r['pitches'],'event':event,'intentional_walk':r['iw']=='1','bunt_contact':r['bunt']=='1'})
                if reason:continue
                for balls,strikes,action,pitch_event in seq:
                    counts[phase][balls,strikes,action,None,None][pitch_event]+=1;pitch_rows+=1
                if phase=='fit':players['retrosheet:'+r['pitcher']]+=len(seq)
        native[year]={p:[[*cell,[[*outcome,n] for outcome,n in c.items()]] for cell,c in cells.items()] for p,cells in moves.items()}
        if richer:
            richer['movements']=native[year]
            richer['used_movements']={p:sum(sum(c.values()) for c in cells.values()) for p,cells in moves.items()}
            richer['movement_source']='Retrosheet; same MLB season and split; replaces, never adds overlapping Gameday movements'
        else:
            roster=[p for p,n in players.most_common(3)]
            if len(roster)<3:continue
            key=f'MLB:{year}:retrosheet'
            value['cohorts'][key]={'league':'MLB','season':year,'source':'retrosheet','source_rows':pitch_rows,
                'pitchers':roster,'pitcher_names':{p:f'기록 기반 투수 {i+1}' for i,p in enumerate(roster)},
                'source_signature':entry['sha256'],'missing':{'pitch_family':pitch_rows,'location':pitch_rows,'speed_mps':pitch_rows},
                'split':split,'counts':{p:[[*cell,dict(c)] for cell,c in cells.items()] for p,cells in counts.items()},
                'movements':native[year],'used_pitches':{p:sum(sum(c.values()) for c in cells.values()) for p,cells in counts.items()},
                'used_movements':{p:sum(sum(c.values()) for c in cells.values()) for p,cells in moves.items()},
                'pitcher_repertoires':{},'movement_source':'Retrosheet',
                'capabilities':{'pitch_family':False,'location':False,'speed':False,'count_actions':True,'running':True}}
        lineage.append({'season':year,'sha256':entry['sha256']})
        print(f'MLB {year} 기존 기록 연결 · 투구 {pitch_rows:,}개',flush=True)
    for c in value['cohorts'].values():
        if c['league']!='MLB':continue
        tables={p:defaultdict(Counter) for p in c['split']}
        for row in all_running:
            phase='fit' if row['date']<c['split']['validation'][0] else 'validation' if row['date']<=c['split']['validation'][1] else 'test' if row['date']<=c['split']['test'][1] else None
            if phase is None:continue
            cell=tuple(row[k] for k in ('outs','bases','balls','strikes','action'));tables[phase][cell][row['outcome']]+=1
        c['running']={p:[[*cell,[[*outcome,n] for outcome,n in counter.items()]] for cell,counter in cells.items()] for p,cells in tables.items()}
    value['sources'].append({'league':'MLB','provider':'Retrosheet','source_url':'https://www.retrosheet.org/downloads/plays.html',
        'credit':'The information used here was obtained free of charge from and is copyrighted by Retrosheet.',
        'signature':content_hash(lineage),'seasons':lineage,'running_plays':len(all_running),
        'selection':'Gameday owns overlapping detailed pitches; Retrosheet owns MLB movements and other count-only years. No duplicate provider summation.'})
    return value
