"""Native tracking worlds: observed positions only, chronological evidence layers."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,gzip,hashlib,json,sqlite3,math,re
from .lineage import checksum,utc_now
from .pitch_normalize import number,identifier,integer,FAMILIES,base_flags
from .batting_directions import approach,narrative_area,handedness,CONTACT

FAMILY={**FAMILIES,'ST':'slider','SV':'curve','CS':'curve','FO':'splitter','FA':'fastball'}
NPB_FAMILY={1:'fastball',31:'fastball',2:'curve',35:'curve',36:'curve',37:'curve',38:'curve',3:'sinker',46:'sinker',47:'sinker',48:'sinker',51:'sinker',4:'slider',32:'slider',33:'slider',34:'slider',52:'slider',5:'splitter',39:'splitter',40:'splitter',6:'sinker',42:'sinker',43:'sinker',7:'changeup',41:'changeup',9:'cutter',49:'cutter',45:'knuckle'}
EVENTS={'single':'single','double':'double','triple':'triple','home_run':'home_run','hit_by_pitch':'hbp'}
DESCRIPTIONS={'ball':('take','ball'),'blocked_ball':('take','ball'),'called_strike':('take','strike'),
 'swinging_strike':('swing','strike'),'swinging_strike_blocked':('swing','strike'),'foul_tip':('swing','strike'),
 'foul':('swing','foul'),'hit_into_play':('swing',None),'hit_by_pitch':('take','hbp'),
 'missed_bunt':('bunt','strike'),'foul_bunt':('bunt','bunt_foul'),'bunt_foul_tip':('bunt','strike')}
COLS=('uid','cohort','date','game','ordering','inning','bottom','balls','strikes','outs','bases','pitcher','hand','action','event','terminal','family','location','speed','home_diff','runs','side','kind')


def cell(x,z):
    if x is None or z is None or not math.isfinite(x) or not math.isfinite(z):return None
    return ('left' if x<1/3 else 'right' if x>2/3 else 'middle')+'_'+('low' if z<1/3 else 'high' if z>2/3 else 'middle')


def npb_position(x,y):
    # Published SPAIA renderer: area 93x116, ds X=200, zone 56x70,
    # centered background; ballStyle uses xRatio for both coordinates.
    if x is None or y is None or x<0 or y<0:return None
    scale=93/200;left=(93-56)/(2*scale);top=(116-70)/(2*scale)
    return cell((x-left)/(56/scale),1-(y-top)/(70/scale))


def event_name(value):
    if value in EVENTS:return EVENTS[value]
    if value and value not in ('strikeout','walk','intent_walk'):return 'out'
    return None


def normalized(row,league,provider):
    if row.get('game_type')!='R':return None
    b,s=integer(row.get('balls')),integer(row.get('strikes'));outs=integer(row.get('outs_when_up'))
    if b not in range(4) or s not in range(3) or outs not in range(3):return None
    desc=row.get('description');action,event=DESCRIPTIONS.get(desc,(None,None))
    if not action:return None
    if desc=='hit_into_play':event=event_name(row.get('events'))
    if event is None:return None
    if row.get('events') in ('sac_bunt','sac_bunt_double_play'):action='bunt'
    date=str(row.get('game_date'))[:10];game=identifier(row.get('game_pk'))
    if not game:return None
    terminal='walk' if event=='ball' and b==3 else 'strikeout' if (event=='strike' or event=='bunt_foul') and s==2 else event if event in (*CONTACT,'hbp') else None
    family=FAMILY.get(row.get('pitch_type'))
    if league=='MLB':
        x,z,lo,hi=(number(row.get(k)) for k in ('plate_x','plate_z','sz_bot','sz_top'))
        location=cell((x+17/24)/(17/12),(z-lo)/(hi-lo)) if None not in (x,z,lo,hi) and hi>lo else None
        speed=number(row.get('release_speed'));speed=speed*.44704 if speed else None
    else:
        location=cell(number(row.get('location_x_norm')),number(row.get('location_z_norm')))
        speed=number(row.get('speed_kmh'));speed=speed/3.6 if speed else None
    ab=integer(row.get('at_bat_number')) or integer(row.get('relay_no')) or 0
    seq=integer(row.get('pitch_number'));order=ab*1000+(seq or 0)
    uid=row.get('pitch_uid') or row.get('pitch_key') or str(game)+':'+str(ab)+':'+str(seq)
    home,away=number(row.get('home_score')),number(row.get('away_score'))
    text=str(row.get('des') or '')
    if league=='KBO':side=narrative_area(text,league)
    else:
        lower=text.lower();side=next((v for words,v in [(('left field','to left','to shortstop','to third'),'left'),(('center field','to center','to pitcher'),'center'),(('right field','to right','to first','to second'),'right')] if any(w in lower for w in words)),None)
    kind={'ground_ball':'ground','fly_ball':'fly','line_drive':'line','popup':'popup'}.get(row.get('bb_type'))
    return (provider+':'+str(uid),f'{league}:{date[:4]}:{provider}',date,provider+':'+game,order,integer(row.get('inning')),
      int(row.get('inning_topbot')=='Bot'),b,s,outs,base_flags([row.get('on_1b'),row.get('on_2b'),row.get('on_3b')]),
      provider+':'+str(identifier(row.get('pitcher'))),handedness(row.get('stand')),action,event,terminal,family,location,speed,
      home-away if None not in (home,away) else None,None,side,kind)


def insert_unique(db,rows,quality,quarantined):
    """One physical key once; quarantine every conflicting normalized version."""
    sql='INSERT INTO p VALUES ('+','.join('?' for _ in COLS)+')'
    for row in rows:
        if row[0] in quarantined:continue
        try:db.execute(sql,row)
        except sqlite3.IntegrityError:
            previous=db.execute('SELECT * FROM p WHERE uid=?',(row[0],)).fetchone()
            league=row[1].split(':')[0]
            if previous is not None and tuple(previous)==tuple(row):quality[league]['duplicate_normalized_rows']+=1
            else:
                quality[league]['conflicting_pitch_ids']+=1
                db.execute('DELETE FROM p WHERE uid=?',(row[0],))
                db.execute('INSERT OR IGNORE INTO conflicts VALUES (?)',(row[0],));quarantined.add(row[0])


def prepare(root,output):
    import pyarrow.parquet as pq
    from .pitch_corpus import transition_between
    from .corpus_measurements import cutpoints,band
    from baseball_lab.experiments.match.pitch_game.corpus_world import corpus
    root=Path(root).resolve();output=Path(output)
    if output.exists():raise FileExistsError('기존 추적 자료를 덮어쓰지 않습니다.')
    folder=output.parent/(output.stem+'-work');folder.mkdir(parents=True,exist_ok=False)
    db=sqlite3.connect(folder/'observations.sqlite');db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF')
    db.execute('CREATE TABLE p ('+','.join(c+(' INTEGER' if c in ('ordering','inning','bottom','balls','strikes','outs','bases') else ' REAL' if c in ('speed','home_diff','runs') else ' TEXT')+(' PRIMARY KEY' if c=='uid' else '') for c in COLS)+')')
    quality=defaultdict(Counter);sources=[];pending=[]
    db.execute('CREATE TABLE conflicts (uid TEXT PRIMARY KEY)');quarantined=set()
    def flush():
        nonlocal pending
        insert_unique(db,pending,quality,quarantined)
        db.commit();pending=[]
    manifests=[p for p in (root/'data/local/tracking-releases').glob('*/manifest.json') if json.loads(p.read_text())['status']=='ACQUIRED']
    for path in manifests:
        m=json.loads(path.read_text());league=m['release']['league'];repo=m['release']['repository'];provider='public-statcast-v4' if repo.startswith('s903124') else 'public-statcast-tracking-v2' if league=='MLB' else 'ekim-naver-locations-v1'
        sources.append({'league':league,'repository':repo,'release':m['release'],'manifest_sha256':checksum(path),'files':[{k:v for k,v in f.items() if k in ('name','sha256','bytes')} for f in m['files']],'rights_status':m['rights_status']})
        for f in m['files']:
            p=root/f['path'];name=f['name']
            if not (name.lower().startswith('statcast_') or name.startswith('kbo_LOTTE')):continue
            if checksum(p)!=f['sha256']:raise ValueError('추적 원본 지문 불일치')
            if p.suffix=='.parquet':
                wanted=['game_type','balls','strikes','outs_when_up','description','events','game_date','game_pk','pitch_type','plate_x','plate_z','sz_bot','sz_top','release_speed','at_bat_number','pitch_number','pitch_uid','home_score','away_score','des','bb_type','inning','inning_topbot','on_1b','on_2b','on_3b','pitcher','stand']
                reader=(row for batch in pq.ParquetFile(p).iter_batches(batch_size=16384,columns=wanted) for row in batch.to_pylist())
                stream=None
            else:stream=p.open(encoding='utf-8-sig',newline='');reader=csv.DictReader(stream)
            for raw in reader:
                quality[league]['raw_rows']+=1;row=normalized(raw,league,provider)
                if row is None:quality[league]['unsupported_or_nonregular']+=1;continue
                pending.append(row)
                if len(pending)>=20000:
                    flush()
            if stream:stream.close()
            print('정규화 '+name,flush=True)
    if pending:flush()
    # Existing NPB originals contain measured display positions, not just prose.
    base=corpus();npb_meta=next(p for p in (root/'data/local/pitch-corpus').glob('*/manifest.json') if json.loads(p.read_text())['league']=='NPB')
    meta=json.loads(npb_meta.read_text());original=sqlite3.connect(f'file:{npb_meta.parent/"pitches.sqlite"}?mode=ro',uri=True);original.row_factory=sqlite3.Row
    if checksum(npb_meta.parent/'pitches.sqlite')!=meta['database_sha256']:raise ValueError('NPB 원본 정규화 DB 지문 불일치')
    for r in original.execute('SELECT * FROM pitches'):
        family=r['pitch_family'] or NPB_FAMILY.get(integer(r['raw_type']));location=npb_position(r['raw_x'],r['raw_z'])
        row=(r['id'],r['cohort'],r['date'],r['game'],r['ordering'],r['inning'],r['bottom'],r['balls'],r['strikes'],r['outs'],r['bases'],r['pitcher'],'U',r['observed_action'],r['event'],r['terminal'],family,location,r['speed_mps'],r['home_difference'],r['runs'],None,None)
        pending.append(row);quality['NPB']['raw_rows']+=1
        if len(pending)>=20000:flush()
    if pending:flush()
    original.close();sources.append({'league':'NPB','repository':'armstjc/Nippon-Baseball-Data-Repository','source_signature':meta['signature'],'file_count':len(meta['files']),
      'renderer_url':'https://gs-files.spaia.jp/js/npb/pc/pc.one-ball.v0.3.5.bundle.js','renderer_sha256':checksum(root/'data/local/tracking-definitions/npb-renderer.js'),'frame':'SPAIA centered 56x70 zone inside 93x116 area, raw X domain200; pixel display only'})
    db.execute('CREATE INDEX native_order ON p(game,ordering)');db.execute('CREATE INDEX cohort_date ON p(cohort,date)');db.commit();db.row_factory=sqlite3.Row
    cohorts={};contacts={};phasecuts={};profiles={};counts={};movements={};contactcounts={};hands={};speedhists=defaultdict(Counter)
    for key,lo,hi in db.execute('SELECT cohort,MIN(date),MAX(date) FROM p GROUP BY cohort'):
        league,year,provider=key.split(':',2);days=[x[0] for x in db.execute('SELECT DISTINCT date FROM p WHERE cohort=? ORDER BY date',(key,))]
        if len(days)<10:continue
        a=max(1,int(len(days)*.6));b=min(len(days)-1,max(2,int(len(days)*.8)));split={'fit':[days[0],days[a-1]],'validation':[days[a],days[b-1]],'test':[days[b],days[-1]]}
        if league=='NPB':split=base['cohorts'][key]['split']
        phasecuts[key]=split
        counts[key]={p:defaultdict(Counter) for p in split};movements[key]={p:defaultdict(Counter) for p in split};contactcounts[key]={p:Counter() for p in split};hands[key]={p:Counter() for p in split};profiles[key]=defaultdict(Counter)
        players=[r[0] for r in db.execute('SELECT pitcher,COUNT(*) n FROM p WHERE cohort=? AND date<? AND family IS NOT NULL AND location IS NOT NULL AND speed>0 GROUP BY pitcher ORDER BY n DESC LIMIT 3',(key,split['validation'][0]))]
        cohorts[key]={'league':league,'season':int(year),'source':provider,'split':split,'pitchers':players,'pitcher_names':{p:'추적 명단 '+str(i+1) for i,p in enumerate(players)},'source_rows':0}
    for r in db.execute('SELECT cohort,date,family,speed FROM p WHERE family IS NOT NULL AND location IS NOT NULL AND speed>0'):
        if r['cohort'] in phasecuts and r['date']<phasecuts[r['cohort']]['validation'][0]:speedhists[r['cohort'],r['family']][r['speed']]+=1
    cuts={k:cutpoints(v) for k,v in speedhists.items()}
    previous=None
    for r in db.execute('SELECT * FROM p ORDER BY game,ordering'):
        key=r['cohort']
        if key not in cohorts:previous=r;continue
        c=cohorts[key];part=next((p for p,(lo,hi) in c['split'].items() if lo<=r['date']<=hi),None)
        if not part:previous=r;continue
        c['source_rows']+=1
        speed=band(r['speed'],cuts.get((key,r['family'])))
        if r['family'] and r['location'] and speed and r['action'] and r['event']:
            counts[key][part][r['balls'],r['strikes'],r['action'],r['family'],r['location'],speed][r['event']]+=1
            if part=='fit' and r['pitcher'] in c['pitchers']:profiles[key][r['pitcher']][r['family']+'|'+str(speed)]+=1
            quality[c['league']]['course_rows']+=1
        else:quality[c['league']]['not_course_eligible']+=1
        if r['ordering']%1000==1:hands[key][part][r['hand']]+=1
        if r['event'] in CONTACT and r['action']=='swing':
            contactcounts[key][part][r['balls'],r['strikes'],r['hand'],approach(r['side'],r['hand']),r['side'],r['kind'],r['event']]+=1
        if previous and previous['terminal'] and previous['game']==r['game'] and r['balls']==0 and r['strikes']==0 and re.search(r'[-:]1$',r['uid']):
            old=previous;half=old['inning']*2+old['bottom'];new=r['inning']*2+r['bottom'];runs=old['runs']
            if runs is None and old['home_diff'] is not None and r['home_diff'] is not None:runs=(r['home_diff']-old['home_diff'])*(1 if old['bottom'] else -1)
            delta=r['outs']-old['outs'] if new==half else 3-old['outs'];end=r['bases'] if new==half else 0
            population=1+old['bases'].bit_count()
            if (old['cohort']==key and c['split'][part][0]<=old['date'] and new in (half,half+1) and runs is not None and int(runs)==runs and 0<=runs<=4 and 0<=delta<=3-old['outs']
                and (delta+end.bit_count()+runs==population if old['outs']+delta<3 else delta+runs<=population)):
                movements[key][part][old['outs'],old['bases'],old['terminal'],old['action']=='bunt'][delta,end,int(runs)]+=1
        previous=r
    from baseball_lab.experiments.match.pitch_game.directional_contact import directions
    oldcontacts=directions()
    for key,c in cohorts.items():
        c['counts']={p:[[*cell,dict(n)] for cell,n in cells.items()] for p,cells in counts[key].items()};c['movements']={p:[[*cell,[[*outcome,n] for outcome,n in v.items()]] for cell,v in cells.items()] for p,cells in movements[key].items()}
        c['used_pitches']={p:sum(sum(v.values()) for v in values.values()) for p,values in counts[key].items()};c['used_movements']={p:sum(sum(v.values()) for v in values.values()) for p,values in movements[key].items()}
        c['pitcher_speed_repertoires']={p:dict(v) for p,v in profiles[key].items()};c['pitcher_repertoires']={p:dict(Counter({f:sum(n for k,n in v.items() if k.split('|')[0]==f) for f in {k.split('|')[0] for k in v}})) for p,v in profiles[key].items()}
        c['speed_cutpoints_mps']={f:v for (co,f),v in cuts.items() if co==key};c['speed_fit_summary']={}
        if c['league']=='NPB':
            c['running']=base['cohorts'][key].get('running',{});contacts[key]=oldcontacts['cohorts'][key]
        else:
            contacts[key]={'split':c['split'],'counts':{p:[[*cell,n] for cell,n in values.items()] for p,values in contactcounts[key].items()},'hand_counts':{p:dict(v) for p,v in hands[key].items()},
                'coverage':{p:{'contact_rows':sum(v.values()),'area_unknown':sum(n for cell,n in v.items() if cell[4] is None),'stance_unknown':sum(n for cell,n in v.items() if cell[2]=='U')} for p,v in contactcounts[key].items()}}
            # Same-year observed running is available for old MLB seasons only.
            match=next((v for v in base['cohorts'].values() if v['league']==c['league'] and v['season']==c['season'] and v['split']==c['split']),None)
            c['running']=match.get('running',{}) if match else {}
    ready={k:v for k,v in cohorts.items() if len(v['pitchers'])==3 and all(v['used_pitches'][p]>=100 for p in v['split'])}
    value={'schema':'observed-tracking-worlds-v1','source_status':'REAL_OBSERVED','created_at':utc_now(),'cohorts':ready,'contacts':{k:contacts[k] for k in ready},'sources':sources,'quality':{k:dict(v) for k,v in quality.items()},
       'assumptions':['Only observed pitch family, location and speed enter the course study. Excluded rows and original releases are retained, never imputed.',
       'Coordinates are normalized within each published source frame; left/right are source-display directions, not verified identical physical sensors.',
       'MLB 2026 ABS/mid-plate conventions remain a separate league/year cohort. KBO 2026 covers Lotte-participant games, not the full league.',
       'SPAIA pixel coordinates are normalized using its published renderer geometry and pitch-type dictionary; no pixel is called a metre.',
       'Conditional outcome probabilities and directional targets are observational approximations, not identified causal strategy effects.']}
    db.close();body=gzip.compress(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode(),mtime=0);output.write_bytes(body)
    return {'sha256':checksum(output),'bytes':len(body),'cohorts':len(ready),'quality':value['quality'],'coverage':{l:sorted(v['season'] for v in ready.values() if v['league']==l) for l in ('MLB','KBO','NPB')}}
