"""One corpus with field-level capabilities; missing tracking never drops a season."""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import csv,gzip,json,sqlite3
from .lineage import checksum,utc_now
from .corpus_measurements import band,cutpoints
from .tracking_corpus import cell,FAMILY,event_name
from .pitch_normalize import number,integer
from .batting_directions import handedness,CONTACT


def supplementary_contacts(root,split,hands):
    """Keep Lotte directional observations without double-counting HF pitches."""
    from .tracking_corpus import normalized,COLS
    m=json.loads(next((root/'data/local/tracking-releases').glob('kbo-*/manifest.json')).read_text())
    counts={p:Counter() for p in split}
    for f in m['files']:
        path=root/f['path']
        if checksum(path)!=f['sha256']:raise ValueError('KBO 방향 보조 원본 지문 불일치')
        with path.open(encoding='utf-8-sig',newline='') as stream:
            for raw in csv.DictReader(stream):
                row=normalized(raw,'KBO','ekim-naver-locations-v1')
                if row is None:continue
                r=dict(zip(COLS,row));part=next((p for p,(lo,hi) in split.items() if lo<=r['date']<=hi),None)
                if part and r['event'] in CONTACT and r['action']=='swing':
                    from .batting_directions import approach
                    counts[part][r['balls'],r['strikes'],r['hand'],approach(r['side'],r['hand']),r['side'],r['kind'],r['event']]+=1
    return {'split':split,'counts':{p:[[*cell,n] for cell,n in v.items()] for p,v in counts.items()},'hand_counts':{p:dict(v) for p,v in hands.items()},
        'coverage':{p:{'contact_rows':sum(v.values()),'area_unknown':sum(n for cell,n in v.items() if cell[4] is None),'stance_unknown':sum(n for cell,n in v.items() if cell[2]=='U')} for p,v in counts.items()},
        'population':'Supplementary observed directions: 2026 Lotte-participant 144 games; not full-league contact coverage.'}


def supplementary_movements(root,split):
    """Per-pitch native movement samples; PA-start runners are not pitch state."""
    from .tracking_corpus import normalized,COLS
    from .pitch_corpus import transition_between
    m=json.loads(next((root/'data/local/tracking-releases').glob('kbo-*/manifest.json')).read_text())
    rows=[];counts={p:defaultdict(Counter) for p in split}
    for f in m['files']:
        path=root/f['path']
        if checksum(path)!=f['sha256']:raise ValueError('KBO 진루 보조 원본 지문 불일치')
        with path.open(encoding='utf-8-sig',newline='') as stream:
            for raw in csv.DictReader(stream):
                row=normalized(raw,'KBO','ekim-naver-locations-v1')
                if row is None:continue
                r=dict(zip(COLS,row));r['sequence']=integer(raw.get('pitch_number'));r['home_difference']=r['home_diff'];rows.append(r)
    previous=None
    for r in sorted(rows,key=lambda r:(r['game'],r['ordering'])):
        if previous and previous['terminal']:
            part=next((p for p,(lo,hi) in split.items() if lo<=previous['date']<=hi),None)
            outcome=transition_between(previous,r)
            if part and outcome:counts[part][previous['outs'],previous['bases'],previous['terminal'],previous['action']=='bunt'][outcome]+=1
        previous=r
    return ({p:[[*cell,[[*target,n] for target,n in v.items()]] for cell,v in rows.items()] for p,rows in counts.items()},
            {p:sum(sum(v.values()) for v in rows.values()) for p,rows in counts.items()})


def hf_pitch(row):
    """Source counts are pre-pitch; PA outcomes repeat, so read only H for BIP."""
    if not integer(row.get('pitch_number')):return None
    action,event={'B':('take','ball'),'T':('take','strike'),'S':('swing','strike'),'F':('swing','foul'),
                  'V':('bunt','strike'),'W':('bunt','bunt_foul')}.get(row.get('pitch_result'),(None,None))
    if row.get('pitch_result')=='H':action,event=('bunt' if row.get('events')=='sac_bunt' else 'swing'),event_name(row.get('events'))
    b,s=integer(row.get('balls')),integer(row.get('strikes'))
    if b not in range(4) or s not in range(3) or not action or event is None:return None
    x,z,lo,hi=(number(row.get(k)) for k in ('plate_x','plate_z','sz_bot','sz_top'))
    location=cell((x+17/24)/(17/12),(z-lo)/(hi-lo)) if None not in (x,z,lo,hi) and hi>lo else None
    speed=number(row.get('release_speed_kmh'));speed=speed/3.6 if speed and 0<speed<288 else None
    return b,s,action,FAMILY.get(row.get('pitch_type')),location,speed,event


def capabilities(c):
    values={p:Counter() for p in c['counts']}
    for part,rows in c['counts'].items():
        for b,s,a,f,l,v,n in rows:
            count=sum(n.values());q=values[part];q['pitches']+=count
            q['family']+=count*bool(f);q['course']+=count*bool(l);q['speed']+=count*bool(v)
    return {p:dict(v) for p,v in values.items()}


def history(root):
    """Different units retain different denominators, never synthetic pitch rows."""
    from importlib.resources import files
    p=files('baseball_lab').joinpath('data/resources/players.json.gz');body=p.read_bytes()
    rows=json.loads(gzip.decompress(body))['rows'];annual=defaultdict(lambda:defaultdict(Counter))
    for r in rows:
        if r['season']<2010 or r['role']!='batter' or r['row_kind']!='season_total':continue
        n=r['counts'].get('PA');counts=r['counts']
        if not n or n<0:continue
        for key in ('H','HR','SO','BB'):
            value=counts.get(key)
            if value is not None and 0<=value<=n:
                annual[r['league'],r['season']][key].update(n=value,d=n)
    source=[{'credit':'Existing canonical season batting counts; original namespaces and source hashes retained in players asset','signature':checksum(Path(str(p)))}]
    manifest=next((root/'data/local/modern-releases').glob('npb-history-*/manifest.json'))
    m=json.loads(manifest.read_text());f=m['files'][0];p=root/f['path']
    if checksum(p)!=f['sha256']:raise ValueError('NPB 과거 통계 지문 불일치')
    seen=set()
    with p.open(encoding='utf-8-sig',newline='') as stream:
        for r in csv.DictReader(stream):
            year=int(r['year']);identity=(year,r['league'],r['team'])
            if identity in seen:raise ValueError('NPB 팀 합계 중복')
            seen.add(identity);games=int(r['G']);runs=int(r['RS'])
            if games!=int(r['W'])+int(r['L'])+int(r['D']) or games<=0 or runs<0:raise ValueError('NPB 팀 경기 수 모순')
            annual['NPB',year]['R_per_team_game'].update(n=runs,d=games)
    source.append({'credit':m['credit'],'repository':m['repository'],'signature':f['sha256'],'source_url':m['source_url']})
    return {l+':'+str(y):{k:dict(v) for k,v in fields.items()} for (l,y),fields in annual.items()},source


def prepare(root,output):
    import pyarrow.parquet as pq
    from baseball_lab.experiments.match.pitch_game.corpus_world import corpus,ASSET_SHA256 as BASE_SHA
    from baseball_lab.experiments.match.pitch_game.tracking_world import data as tracked,ASSET_SHA256 as TRACK_SHA
    from baseball_lab.experiments.match.pitch_game.directional_contact import directions,ASSET_SHA256 as CONTACT_SHA
    root=Path(root).resolve();output=Path(output)
    if output.exists():raise FileExistsError('기존 통합 교재를 덮어쓰지 않습니다.')
    base=corpus();track=tracked();oldcontacts=directions()['cohorts'];selected={};contacts={};quality={};provenance=[]
    for key,c in base['cohorts'].items():
        if c['season']>=2010:selected[c['league'],c['season']]=(key,deepcopy(c));contacts[key]=deepcopy(oldcontacts[key])
    for key,c in track['cohorts'].items():
        selected[c['league'],c['season']]=(key,deepcopy(c));contacts[key]=deepcopy(track['contacts'][key])
    # Recover partial observations from the same normalized releases. Complete
    # tracking is a capability, not the minimum requirement for all learning.
    database=root/'data/local/observed-tracking-worlds-v1-checked.json-work/observations.sqlite'
    db=sqlite3.connect(f'file:{database}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    counters={key:{p:defaultdict(Counter) for p in c['counts']} for key,c in selected.values() if key in track['cohorts']}
    for r in db.execute('SELECT cohort,date,balls,strikes,action,family,location,speed,event FROM p'):
        key=r['cohort']
        if key not in counters or not r['action'] or not r['event']:continue
        c=selected[tuple([key.split(':')[0],int(key.split(':')[1])])][1]
        part=next((p for p,(lo,hi) in c['split'].items() if lo<=r['date']<=hi),None)
        if not part:continue
        v=band(r['speed'],c['speed_cutpoints_mps'].get(r['family']))
        counters[key][part][r['balls'],r['strikes'],r['action'],r['family'],r['location'],v][r['event']]+=1
    db.close();provenance.append({'kind':'prior normalized observed tracking releases including partial fields','sha256':checksum(database)})
    for key,c in selected.values():
        if key in counters:c['counts']={p:[[*cell,dict(n)] for cell,n in cells.items()] for p,cells in counters[key].items()}
    # Legacy Gameday positions use batter-relative names. Reclassify only from
    # preserved physical x plus already observed height, never swap names blindly.
    meta=next(p for p in (root/'data/local/pitch-corpus').glob('*/manifest.json') if json.loads(p.read_text())['league']=='MLB')
    db=sqlite3.connect(f'file:{meta.parent/"pitches.sqlite"}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    for year in (2015,2016):
        key,c=selected['MLB',year];rows={p:defaultdict(Counter) for p in c['counts']}
        for r in db.execute('SELECT date,balls,strikes,observed_action,pitch_family,location,raw_x,speed_mps,event FROM pitches WHERE cohort=?',(key,)):
            if not r['observed_action'] or not r['event']:continue
            part=next((p for p,(lo,hi) in c['split'].items() if lo<=r['date']<=hi),None)
            if not part:continue
            area=None;x=r['raw_x']
            if r['location'] and x is not None:area=('left' if x<-17/72 else 'right' if x>17/72 else 'middle')+'_'+r['location'].split('_')[1]
            v=band(r['speed_mps'],c['speed_cutpoints_mps'].get(r['pitch_family']))
            rows[part][r['balls'],r['strikes'],r['observed_action'],r['pitch_family'],area,v][r['event']]+=1
        c['counts']={p:[[*cell,dict(n)] for cell,n in cells.items()] for p,cells in rows.items()}
    db.close();provenance.append({'kind':'preserved Gameday physical-coordinate normalization','sha256':checksum(meta.parent/'pitches.sqlite')})
    m=json.loads(next((root/'data/local/modern-releases').glob('kbo-*/manifest.json')).read_text())
    for source in m['files']:
        year=source['year'];path=root/source['path']
        if checksum(path)!=source['sha256']:raise ValueError('KBO 추가 원본 지문 불일치')
        columns=['game_pk','game_date','at_bat_number','pitch_number','pitcher','balls','strikes','pitch_result','events','pitch_type','release_speed_kmh','plate_x','plate_z','sz_bot','sz_top','stand','az']
        raw=pq.read_table(path,columns=columns).to_pylist();key=f'KBO:{year}:slothman-naver-v0';quality[str(year)]={'source_rows':len(raw),'games':len({r['game_pk'] for r in raw}),'no_pitch_rows':0,'unsupported_pitches':0,'az_positive_reported':0}
        prior_key,prior=selected['KBO',year]
        split=deepcopy(prior['split']) if year<2026 else None
        if split is None:
            days=sorted({str(r['game_date'])[:10] for r in raw});a=int(len(days)*.6);b=int(len(days)*.8)
            split={'fit':[days[0],days[a-1]],'validation':[days[a],days[b-1]],'test':[days[b],days[-1]]}
        parsed=[];speeds=defaultdict(Counter);players=Counter();seen=set()
        for r in raw:
            uid=(r['game_pk'],r['at_bat_number'],r['pitch_number'])
            if uid in seen:raise ValueError('KBO 실제 투구 키 중복')
            seen.add(uid);p=hf_pitch(r)
            if not p:quality[str(year)]['no_pitch_rows' if not r['pitch_number'] else 'unsupported_pitches']+=1;continue
            date=str(r['game_date'])[:10];part=next((p for p,(lo,hi) in split.items() if lo<=date<=hi),None)
            if not part:continue
            parsed.append((r,p,part));b,s,action,f,loc,speed,event=p
            if part=='fit':
                players[r['pitcher']]+=1
                if f and speed:speeds[f][speed]+=1
            quality[str(year)]['az_positive_reported']+=bool(number(r.get('az')) is not None and r['az']>0)
        cuts={f:cutpoints(v) for f,v in speeds.items()};pitchers=[key+':'+p for p,n in players.most_common(3)]
        rows={p:defaultdict(Counter) for p in split};profiles=defaultdict(Counter);hands={p:Counter() for p in split}
        for r,p,part in parsed:
            b,s,action,f,loc,speed,event=p;v=band(speed,cuts.get(f));pid=key+':'+r['pitcher']
            rows[part][b,s,action,f,loc,v][event]+=1
            if part=='fit' and pid in pitchers and f:profiles[pid][f+'|'+str(v)]+=1
            if r['pitch_number']==1:hands[part][handedness(r.get('stand'))]+=1
        # HF runners/outs are PA-start fields. Keep the already verified native
        # pitch-state movement source for 2023-25, rather than treating them as
        # current pitch state or double-counting an explicit steal decision.
        movements=deepcopy(prior['movements']);movement_counts=deepcopy(prior['used_movements'])
        if year==2026:movements,movement_counts=supplementary_movements(root,split)
        c={'league':'KBO','season':year,'source':'slothman-naver-v0','source_rows':len(parsed),'split':split,'pitchers':pitchers,'pitcher_names':{p:'관측 명단 '+str(i+1) for i,p in enumerate(pitchers)},
           'counts':{p:[[*cell,dict(n)] for cell,n in cells.items()] for p,cells in rows.items()},
           'movements':movements,'used_movements':movement_counts,
           'movement_source':'NextPitchh native per-pitch state, same league/year and split' if year<2026 else 'Lotte-participant native per-pitch supplement, re-split at full-season boundaries; not full-league movement coverage',
           'pitcher_speed_repertoires':{p:dict(n) for p,n in profiles.items()},'pitcher_repertoires':{p:dict(Counter({f:sum(n for k,n in v.items() if k.split('|')[0]==f) for f in {k.split('|')[0] for k in v}})) for p,v in profiles.items()},
           'speed_cutpoints_mps':cuts,'running':deepcopy(prior.get('running',{})) if split==prior['split'] else {}}
        selected['KBO',year]=(key,c);contacts[key]=deepcopy(contacts[prior_key])
        if year==2026:
            # Directional supplemental evidence is retained separately; no
            # copied full-league contact totals or invented spray coordinates.
            contacts[key]=supplementary_contacts(root,split,hands)
        print('통합 KBO',year,quality[str(year)],flush=True)
    cohorts={k:c for k,c in selected.values()}
    for key,c in cohorts.items():
        c['counts']={p:[row if len(row)==7 else [*row[:5],None,row[-1]] for row in rows] for p,rows in c['counts'].items()}
        c['capabilities']=capabilities(c);c['used_pitches']={p:v['pitches'] for p,v in c['capabilities'].items()}
        if key in contacts and contacts[key]['split']!=c['split']:raise ValueError('타구 교재의 시간 경계 불일치')
    annual,hist_sources=history(root)
    result={'schema':'unified-modern-baseball-v1','source_status':'REAL_OBSERVED','created_at':utc_now(),'start_year':2010,'cohorts':cohorts,
        'contacts':{k:contacts[k] for k in cohorts},'annual_history':annual,'quality':quality,'sources':[*deepcopy(base['sources']),*deepcopy(track['sources']),
         {'repository':m['repository'],'credit':m['credit'],'signature':checksum(next((root/'data/local/modern-releases').glob('kbo-*/manifest.json'))),'files':[{k:v for k,v in f.items() if k!='path'} for f in m['files']]} ,*hist_sources],
        'provenance':{'assets':[BASE_SHA,TRACK_SHA,CONTACT_SHA],'normalized_inputs':provenance},
        'assumptions':['All available pitch records since 2010 train one shared policy pair; no tracking requirement for a whole season.',
        'Missing family, course and speed remain unavailable; only supported choices use those fields. Native transitions are never copied across leagues.',
        'Season aggregates are prior-season context features only, never reconstructed pitch/runner transitions or rewards.',
        'No overlapping provider counts are added for the same league/year/purpose. Existing originals and archived studies are preserved.',
        'KBO 2023-2026 public publisher-derived plate_z uses trajectory reconstruction with reported sensor noise; NPB positions remain display coordinates.',
        'HF KBO PA-start runners/outs are not current pitch state. Native pitch-state movement samples are separate, same league/year; 2026 movement/direction coverage is Lotte-participant games.',
        'Recorded contact targets and pitch patterns remain observational approximations, not identified causal strategy effects.']}
    body=gzip.compress(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode(),mtime=0);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(body)
    return {'sha256':checksum(output),'bytes':len(body),'cohorts':len(cohorts),'pitches':sum(sum(c['used_pitches'].values()) for c in cohorts.values()),'quality':quality}
