"""Source-supported joint pitch/running actions; never invent an unseen pitch.

Definitions: https://www.retrosheet.org/eventfile.htm (pitch codes and running).
Only isolated SB/CS on a recorded called ball/strike are admitted. Pickoffs,
double steals, errors, wild pitches and completed PAs require other models.
"""
import re


def running_play(row, line):
    if row['pa']!='0' or not re.fullmatch(r'(SB[23]|CS[23]\([1-9]+\))',row['event']):return None
    if not re.search(r'>[BC]$',row['pitches']):return None
    count=row['count'].zfill(2)
    if not re.fullmatch(r'[0-3][0-2]',count):return None
    balls,strikes=map(int,count)
    # Completed walk/K + running plays are not in this isolated-play model.
    # Never make a steal command magically avoid a fourth ball or third strike.
    if balls==3 or strikes==2:return None
    event='ball' if row['pitches'][-1]=='B' else 'strike'
    if event=='ball' and balls==3 or event=='strike' and strikes==2:return None
    if any(row.get(k,'0')!='0' for k in ('wp','pb','bk','oa','di')):return None
    target=int(row['event'][2]);start=1<<(target-2);destination=1<<(target-1)
    bases=sum(1<<(i-1) for i in (1,2,3) if row[f'br{i}_pre'])
    if not bases&start or bases&destination:return None
    caught=row['event'].startswith('CS')
    outs=int(row['outs_pre']);delta=int(row['outs_post'])-outs
    if delta!=int(caught) or int(row['runs'])!=0:return None
    expected=(bases&~start)|(0 if caught else destination)
    after=sum(1<<(i-1) for i in (1,2,3) if row[f'br{i}_post'])
    if outs+delta<3 and after!=expected:return None
    # Preserve other runners' identities, not just occupied-base bit counts.
    for base in (1,2,3):
        if base not in (target-1,target) and row[f'br{base}_pre']!=row[f'br{base}_post']:return None
    if not caught and row[f'br{target}_post']!=row[f'br{target-1}_pre']:return None
    return {'record_id':f"{row['gid']}:running:csvline{line}",'game_id':row['gid'],
        'inning':int(row['inning']),'bottom':int(row['vis_home']),'outs':outs,'bases':bases,
        'balls':balls,'strikes':strikes,'action':f'steal_{target}',
        'pitch_event':event,'outs_added':delta,'end_bases':0 if outs+delta==3 else after,
        'runs':0,'source_event':row['event']}
