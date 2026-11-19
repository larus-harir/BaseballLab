"""Explicit stolen-base narration joined to its observed pitch and next state.

Never infer a steal merely from changed bases (wild pitches/errors can do that).
Multiple runner narrations on the same pitch form one joint action, not two
independent probability draws. Unknown/out-of-order joins are excluded.
"""
import csv
from collections import defaultdict,Counter
from .pitch_normalize import npb,integer,identifier


def targets(text):
    if '盗塁' not in text and 'ホームスチール' not in text:return ()
    answer=[]
    for word,target in (('一塁走者',2),('二塁走者',3),('三塁走者',4)):
        if word in text:answer.append(target)
    return tuple(answer)


def join(before,after,notes):
    if not before or not notes or before['terminal'] or before['event'] not in ('ball','strike') or before['observed_action']!='take':return None
    if before['balls']==3 or before['strikes']==2:return None
    if before['game']!=after['game']:return None
    wanted=tuple(sorted({target for note in notes for target in targets(note)}))
    if not wanted or any(not before['bases']&(1<<(target-2)) for target in wanted):return None
    old=before['inning']*2+before['bottom'];new=after['inning']*2+after['bottom']
    if new==old:
        if before['pa']!=after['pa']:return None
        expected=(before['balls']+int(before['event']=='ball'),before['strikes']+int(before['event']=='strike'))
        if (after['balls'],after['strikes'])!=expected:return None
        delta=after['outs']-before['outs'];end=after['bases']
    elif new==old+1:delta=3-before['outs'];end=0
    else:return None
    if not 0<=delta<=len(wanted):return None
    runs=int(4 in wanted and any(('三塁走者' in n or 'ホームスチール' in n) and '成功' in n for n in notes))
    population=before['bases'].bit_count()
    if before['outs']+delta<3 and delta+end.bit_count()+runs!=population:return None
    if before['outs']+delta==3 and delta+runs>population:return None
    return {'date':before['date'],'action':'steal_'+'_'.join(map(str,wanted)),
        'outs':before['outs'],'bases':before['bases'],'balls':before['balls'],'strikes':before['strikes'],
        'pitch_event':before['event'],'outs_added':delta,'end_bases':end,'runs':runs}


def extract(root,source):
    result=[];excluded=Counter()
    for item in source['files']:
        games=defaultdict(list)
        with (root/item['path']).open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row.get('game_id'):games[row['game_id']].append(row)
        for rows in games.values():
            previous=None;pending=[]
            for row in sorted(rows,key=lambda r:integer(r.get('play_id')) or 0):
                text=row.get('description_jap','')
                if targets(text):pending.append(text)
                try:current=npb(row)
                except (ValueError,TypeError,KeyError):continue
                if pending:
                    r=join(previous,current,pending)
                    if r:result.append(r)
                    else:excluded['unsupported_or_unlinked_running_narration']+=1
                previous=current;pending=[]
        print('NPB 주루 연결 · '+item['source_path'],flush=True)
    return result,dict(excluded)
