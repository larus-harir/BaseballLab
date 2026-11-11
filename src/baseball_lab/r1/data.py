"""Normalize Chadwick output, keeping observed transition segments and provenance."""
import csv
from collections import Counter
from pathlib import Path
from baseball_lab.data.lineage import checksum,content_hash,write_json,utc_now

CREDIT='The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711. https://www.retrosheet.org/'
SCHEMA='retrosheet-turn-segments-v1'


def official_rows(path, stats, excluded=None, *, skip_empty_no_play=False):
    """Map documented official fields; retain raw play text, never infer a pitch type."""
    required={'gid','event','inning','vis_home','score_v','score_h','pitches','pa','bunt','iw',
              'outs_pre','outs_post','runs','pn','gametype','pbp',
              *(f'br{i}_{suffix}' for i in (1,2,3) for suffix in ('pre','post'))}
    with Path(path).open(newline='',encoding='utf-8-sig') as file:
        reader=csv.DictReader(file)
        if not required.issubset(reader.fieldnames or []):raise ValueError('공식 플레이 CSV 필수 열이 없습니다.')
        ids=set();previous=None
        for line,row in enumerate(reader,2):
            stats['all_download_rows']+=1
            if row['gametype']!='regular' or row['pbp']!='full':
                stats['excluded_non_regular_or_non_full']+=1;continue
            identity=(row['gid'],row['pn'])
            if identity in ids:raise ValueError(f'Duplicate official play ID: {identity}')
            ids.add(identity)
            if not row['event'] or any(row[name] not in ('0','1') for name in ('pa','iw','bunt')):
                raise ValueError(f'Unsupported official field at CSV line {line}')
            # A redundant post-inning NP is not a playable transition from 3 outs.
            # Keep the original, and record this exact exclusion; never clamp outs.
            if (row['event']=='NP' and row['outs_pre']==row['outs_post']=='3'
                    and row['pa']==row['runs']=='0'
                    and not any(row[f'br{i}_{s}'] for i in (1,2,3) for s in ('pre','post'))):
                stats['excluded_post_inning_no_play']+=1
                if excluded is not None:excluded.append({'source_row_id':f'{row["gid"]}:play{row["pn"]}:csvline{line}',
                                                        'reason':'NP after third out, no PA/runs/runners; not a play'})
                continue
            if (skip_empty_no_play and row['event']=='NP' and not row['pitches']
                    and row['pa']==row['runs']=='0' and row['outs_pre']==row['outs_post']
                    and all(row[f'br{i}_pre']==row[f'br{i}_post'] for i in (1,2,3))):
                stats['excluded_administrative_no_play']+=1
                if excluded is not None:excluded.append({'source_row_id':f'{row["gid"]}:play{row["pn"]}:csvline{line}',
                                                        'reason':'2023 administrative NP, no pitch or state transition'})
                continue
            before,after=int(row['outs_pre']),int(row['outs_post'])
            mapped={'GAME_ID':row['gid'],'INN_CT':row['inning'],'BAT_HOME_ID':row['vis_home'],
                   'OUTS_CT':str(before),'PITCH_SEQ_TX':row['pitches'],
                   'AWAY_SCORE_CT':row['score_v'],'HOME_SCORE_CT':row['score_h'],
                   'EVENT_CODE_TX':row['event'],'IS_IW':'T' if row['iw']=='1' else 'F',
                   'BAT_EVENT_FL':'T' if row['pa']=='1' else 'F','EVENT_OUTS_CT':str(after-before),
                   'BUNT_FL':'T' if row['bunt']=='1' else 'F','INN_END_FL':'T' if after==3 else 'F',
                   'PA_NEW_FL':'F','START_BASES_CD':str(sum(1<<(i-1) for i in (1,2,3) if row[f'br{i}_pre'])),
                   'END_BASES_CD':str(sum(1<<(i-1) for i in (1,2,3) if row[f'br{i}_post'])),
                   'EVENT_RUNS_CT':row['runs'],'SOURCE_ROW_ID':f'{row["gid"]}:play{row["pn"]}:csvline{line}'}
            if previous is not None:
                previous['GAME_END_FL']='T' if previous['GAME_ID']!=mapped['GAME_ID'] else 'F'
                yield previous
            previous=mapped
        if previous is not None:
            previous['GAME_END_FL']='T'
            yield previous


def walk(bases):
    first,second,third=(bool(bases&(1<<i)) for i in range(3))
    return int(True)+2*int(first or second)+4*int(third or(first and second)),int(first and second and third)


def normalize(csv_path,output,source,*,test_only=False,official=False,skip_empty_no_play=False,persist=True):
    csv_path=Path(csv_path);output=Path(output)
    records=[];pending=[];last_half=None;seen=set();errors=Counter();total=0;sequence_bad=0
    previous=None;score_mismatches=0;official_stats=Counter();source_exclusions=[]
    with csv_path.open(newline='',encoding='utf-8') as file:
        reader=official_rows(csv_path,official_stats,source_exclusions,skip_empty_no_play=skip_empty_no_play) if official else csv.DictReader(file)
        for ordinal,row in enumerate(reader,1):
            total+=1
            half=(row['GAME_ID'],int(row['INN_CT']),int(row['BAT_HOME_ID']))
            score=(int(row['AWAY_SCORE_CT']),int(row['HOME_SCORE_CT']))
            outs,base=int(row['OUTS_CT']),int(row['START_BASES_CD'])
            added,runs,end=int(row['EVENT_OUTS_CT']),int(row['EVENT_RUNS_CT']),int(row['END_BASES_CD'])
            if not (0<=outs<=2 and 0<=base<=7 and 0<=end<=7 and 0<=added<=3 and outs+added<=3 and 0<=runs<=4):
                raise ValueError(f'Invalid observed transition at {row["GAME_ID"]}:{ordinal}')
            if previous and half==last_half and previous['end_inning'] is False:
                sequence_bad+=previous['outs']!=outs or previous['bases']!=base
                score_mismatches+=previous['score']!=score
            if half!=last_half:
                if pending:errors['incomplete_segment']+=1;pending=[]
            if row['PA_NEW_FL']=='T' and pending:
                errors['incomplete_segment']+=1;pending=[]
            pending.append((ordinal,row))
            score_after=list(score);score_after[half[2]]+=runs
            previous={'outs':outs+added,'bases':end,'end_inning':row['INN_END_FL']=='T','score':tuple(score_after)};last_half=half
            terminal=row['BAT_EVENT_FL']=='T' or row['INN_END_FL']=='T' or row.get('GAME_END_FL')=='T'
            if not terminal:continue
            first=pending[0][1]
            key=f"{row['GAME_ID']}:{pending[0][0]}-{ordinal}"
            if key in seen:raise ValueError('Duplicate event segment')
            seen.add(key)
            event_codes=[r['EVENT_CODE_TX'] if 'EVENT_CODE_TX' in r else int(r['EVENT_CD']) for _,r in pending]
            bunt=any(r['BUNT_FL']=='T' or any(c in r['PITCH_SEQ_TX'] for c in 'LMO') for _,r in pending)
            # Sacrifice success alone is not the action label: missed/fouled bunts are included.
            record={'record_id':key,'game_id':row['GAME_ID'],'date':f"{row['GAME_ID'][3:7]}-{row['GAME_ID'][7:9]}-{row['GAME_ID'][9:11]}",
                    'inning':half[1],'bottom':half[2], 'outs':int(first['OUTS_CT']),'bases':int(first['START_BASES_CD']),
                    'outs_added':sum(int(r['EVENT_OUTS_CT']) for _,r in pending),
                    'runs':sum(int(r['EVENT_RUNS_CT']) for _,r in pending),'end_bases':end,
                    'action':'bunt_attempt' if bunt else 'ordinary_turn','intentional_walk':15 in event_codes or any(r.get('IS_IW')=='T' for _,r in pending),
                    'truncated':row['BAT_EVENT_FL']!='T','event_codes':event_codes,
                    'source_status':'MOCK_TEST_ONLY' if test_only else 'REAL_OBSERVED','source_row_ids':[r.get('SOURCE_ROW_ID',f'{row["GAME_ID"]}:{i}') for i,r in pending]}
            if record['outs']+record['outs_added']>3:raise ValueError('Segment crosses inning boundary')
            records.append(record);pending=[]
    if pending:errors['incomplete_segment']+=1
    if sequence_bad or score_mismatches:raise ValueError(f'Observed sequence mismatch: bases/outs={sequence_bad}, score={score_mismatches}')
    if not records:raise ValueError('No real segments')
    iw=[r for r in records if r['intentional_walk']]
    iw_matches=sum(walk(r['bases'])==(r['end_bases'],r['runs']) and r['outs_added']==0 for r in iw)
    isolated=[r for r in iw if len(r['event_codes'])==1]
    isolated_matches=sum(walk(r['bases'])==(r['end_bases'],r['runs']) and r['outs_added']==0 for r in isolated)
    if not test_only and (not isolated or len(isolated)!=isolated_matches):
        raise ValueError('Isolated observed intentional walks do not verify the force-walk rule')
    manifest={'schema':SCHEMA,'source_status':'REAL_OBSERVED','acquired_at':utc_now(),**source,'credit':CREDIT,
              'parsed_csv_path':str(csv_path.resolve()),'parsed_csv_sha256':checksum(csv_path),
              'raw_event_rows':total,'used_segments':len(records),'games':len({r['game_id'] for r in records}),
              'dates':[min(r['date'] for r in records),max(r['date'] for r in records)],'exclusions':dict(errors),
              'sequence_mismatches':sequence_bad,'intentional_walks':len(iw),'intentional_walk_rule_matches':iw_matches,
              'download_filter_counts':dict(official_stats),
              'source_exclusions':source_exclusions,
              'score_sequence_mismatches':score_mismatches,'isolated_intentional_walks':len(isolated),
              'isolated_intentional_walk_rule_matches':isolated_matches,
              'missing_features':['pitch type','pitch location','velocity','swing intention','player ability','fatigue'],
              'records_checksum':content_hash(records)}
    manifest['source_status']='MOCK_TEST_ONLY' if test_only else 'REAL_OBSERVED'
    manifest['dataset_id']=content_hash({k:manifest[k] for k in ('schema','records_checksum','parsed_csv_sha256')})
    if persist:write_json(output/'dataset.json',{'manifest':manifest,'records':records})
    return {'manifest':manifest,'records':records}


def load(path):
    import json
    path=Path(path)
    data=json.loads(path.read_text(encoding='utf-8'));m=data['manifest']
    for source in [m['parsed_csv_path'],m.get('terms_path'),*[r['path'] for r in m.get('raw_files',[])]]:
        if source and not Path(source).resolve().is_relative_to(path.parent.resolve()):
            raise ValueError('원천 파일의 보관 폴더 밖 경로를 거부했습니다.')
    if m['schema']!=SCHEMA or m['source_status']!='REAL_OBSERVED' or content_hash(data['records'])!=m['records_checksum']:
        raise ValueError('Dataset integrity/status mismatch')
    if checksum(Path(m['parsed_csv_path']))!=m['parsed_csv_sha256']:raise ValueError('Parsed source checksum mismatch')
    for raw in m.get('raw_files',[]):
        if checksum(Path(raw['path']))!=raw['sha256']:raise ValueError('Original raw source changed')
    if m.get('terms_path') and checksum(Path(m['terms_path']))!=m['terms_sha256']:
        raise ValueError('Source terms changed')
    return data
