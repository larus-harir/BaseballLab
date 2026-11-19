"""Disk-streamed pitch corpus and sufficient statistics, not seasonal-rate mixing."""
import csv,hashlib,json,sqlite3,secrets
from collections import Counter,defaultdict
from functools import lru_cache
from pathlib import Path
from . import pitch_normalize as adapter
from .lineage import checksum,content_hash,write_json,utc_now
from .warehouse import local_path
from .protection import private

COLS=('id','cohort','date','game','pa','sequence','ordering','inning','bottom','balls','strikes','outs','bases',
      'pitcher','batter','observed_action','event','terminal','pitch_family','location','speed_mps',
      'coordinate_system','x_m','z_m','raw_x','raw_z','raw_type','raw_code','runs','home_difference','bat_score','file_id','line','fingerprint')
INTS={'sequence','ordering','inning','bottom','balls','strikes','outs','bases','runs','file_id','line'}
FLOATS={'speed_mps','x_m','z_m','raw_x','raw_z','home_difference','bat_score'}


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        yield from enumerate(csv.DictReader(f),2)


def normalized_rows(root,source,folder):
    league=source['league'];files=source['files']
    if league=='MLB':
        lookup=sqlite3.connect(folder/'atbats.sqlite')
        lookup.execute('CREATE TABLE ab (id TEXT PRIMARY KEY, payload TEXT)')
        for item in files:
            if not item['source_path'].endswith('atbats.csv'):continue
            lookup.executemany('INSERT INTO ab VALUES (?,?)',((adapter.identifier(r['ab_id']),json.dumps(r)) for _,r in rows(root/item['path'])))
        lookup.commit()
        @lru_cache(maxsize=2048)
        def at_bat(key):
            r=lookup.execute('SELECT payload FROM ab WHERE id=?',(key,)).fetchone()
            return json.loads(r[0]) if r else None
        games={adapter.identifier(r['g_id']):r for item in files if item['source_path'].endswith('games.csv') for _,r in rows(root/item['path'])}
        for file_id,item in enumerate(files):
            if not item['source_path'].endswith('pitches.csv'):continue
            for line,row in rows(root/item['path']):
                ab=at_bat(adapter.identifier(row['ab_id']))
                try:
                    r=adapter.mlb(row,ab,games.get(adapter.identifier(ab['g_id'])) if ab else None)
                    if r['sequence'] is None or r['sequence']<1:raise ValueError('not_a_pitch')
                    r['home_difference']=(adapter.number(row.get('b_score'))-adapter.number(ab['p_score']))*(1 if r['bottom'] else -1)
                    yield r,file_id,line,int(adapter.identifier(row['ab_id']))*1000+r['sequence']
                except (ValueError,TypeError,KeyError) as e:yield str(e),file_id,line,None
        lookup.close()
    elif league=='KBO':
        from .pitch_sources import download
        # The release explicitly labels game scope; do not infer it from a date.
        evidence=folder/'game_index.csv'
        if not evidence.exists():download(f'https://raw.githubusercontent.com/{source["repository"]}/{source["revision"]}/data/game_ids/game_index.csv',evidence,4*1024*1024)
        games={r['game_id']:r for _,r in rows(evidence)}
        for file_id,item in enumerate(files):
            if not item['source_path'].startswith('data/pbp_full/'):continue
            previous=None
            for line,row in rows(root/item['path']):
                try:yield adapter.kbo(row,previous,line,games.get(row['game_id'],{})),file_id,line,line
                except (ValueError,TypeError,KeyError) as e:yield str(e),file_id,line,None
                previous=row
    else:
        for file_id,item in enumerate(files):
            for line,row in rows(root/item['path']):
                try:yield adapter.npb(row),file_id,line,adapter.integer(row.get('play_id')) or line
                except (ValueError,TypeError,KeyError) as e:yield str(e),file_id,line,None


def normalize(root,manifest):
    root=Path(root).resolve();manifest=local_path(root,Path(manifest).resolve())
    source=json.loads(manifest.read_text(encoding='utf-8'))
    if source['status']!='ACQUIRED':raise ValueError('수집이 완료된 배포본만 정규화합니다.')
    signature=content_hash({'files':[(f['source_path'],f['sha256']) for f in source['files']],
                            'adapter':checksum(Path(adapter.__file__)),'corpus':checksum(Path(__file__))})
    base=local_path(root,root/'data/local/pitch-corpus');private(base,directory=True)
    for m in base.glob('*/manifest.json'):
        v=json.loads(m.read_text(encoding='utf-8'))
        if v.get('signature')==signature and v.get('status')=='NORMALIZED':
            if checksum(m.parent/'pitches.sqlite')!=v['database_sha256']:raise ValueError('정규화 자료 지문 불일치')
            return m
    for item in source['files']:
        if checksum(local_path(root,root/item['path']))!=item['sha256']:raise ValueError('투구 원본 지문 불일치')
    folder=base/(source['league'].lower()+'-'+signature[:12]+'-'+secrets.token_hex(3));private(folder,directory=True)
    dbfile=folder/'pitches.sqlite';db=sqlite3.connect(dbfile)
    db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF')
    db.execute('CREATE TABLE pitches ('+','.join(c+' '+('INTEGER' if c in INTS else 'REAL' if c in FLOATS else 'TEXT')+(' PRIMARY KEY' if c=='id' else '') for c in COLS)+')')
    db.execute('CREATE TABLE conflicts (id TEXT PRIMARY KEY)')
    sql='INSERT INTO pitches VALUES ('+','.join('?' for _ in COLS)+')'
    stats=defaultdict(lambda:{'rows':0,'dates':set(),'games':set(),'missing':Counter(),'families':Counter(),'actions':Counter()})
    excluded=Counter();examples=[];duplicate=0;conflicts=0;total=0
    for row,file_id,line,ordering in normalized_rows(root,source,folder):
        total+=1
        if isinstance(row,str):
            excluded[row]+=1
            if len(examples)<12:examples.append({'file':file_id,'line':line,'reason':row})
            continue
        identity=row['game']+':'+(str(line) if source['league']=='KBO' else row['pa']+':'+str(row['sequence']))
        cohort=f"{row['league']}:{row['season']}:{row['namespace']}"
        values={**row,'id':identity,'cohort':cohort,'ordering':ordering,'file_id':file_id,'line':line}
        values['fingerprint']=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if db.execute('SELECT 1 FROM conflicts WHERE id=?',(identity,)).fetchone():continue
        try:db.execute(sql,tuple(values.get(k) for k in COLS))
        except sqlite3.IntegrityError:
            previous=db.execute('SELECT fingerprint FROM pitches WHERE id=?',(identity,)).fetchone()
            if previous and previous[0]==values['fingerprint']:duplicate+=1
            else:
                conflicts+=1;db.execute('DELETE FROM pitches WHERE id=?',(identity,));db.execute('INSERT OR IGNORE INTO conflicts VALUES (?)',(identity,))
            continue
        s=stats[cohort];s['rows']+=1;s['dates'].add(row['date']);s['games'].add(row['game'])
        s['missing'].update(row['missing'].keys());s['families'][row['pitch_family'] or 'unresolved']+=1;s['actions'][row['observed_action'] or 'unresolved']+=1
        if total%100000==0:db.commit();print(f'{source["league"]} 정규화 · 원본 {total:,}행',flush=True)
    db.commit();db.execute('CREATE INDEX chronology ON pitches(cohort,date,game,ordering)');db.execute('CREATE INDEX game_order ON pitches(game,ordering)');db.commit()
    actual=dict(db.execute('SELECT cohort,COUNT(*) FROM pitches GROUP BY cohort'));db.close();private(dbfile)
    cohorts={k:{'rows':actual.get(k,0),'dates':sorted(s['dates']),'games':len(s['games']),
        'missing':dict(s['missing']),'pitch_families':dict(s['families']),'observed_actions':dict(s['actions'])} for k,s in stats.items()}
    result={'schema':adapter.SCHEMA,'status':'NORMALIZED','created_at':utc_now(),'signature':signature,
        'league':source['league'],'source_manifest':str(manifest.relative_to(root)),'source_manifest_sha256':checksum(manifest),
        'files':source['files'],'database_sha256':checksum(dbfile),'raw_rows':total,'normalized_rows':sum(actual.values()),
        'excluded':dict(excluded),'exclusion_examples':examples,'exact_duplicates':duplicate,'conflicting_ids_quarantined':conflicts,
        'cohorts':cohorts,'units':{'speed_mps':'metres/second','x_m':'metres; MLB physical coordinates only','z_m':'metres; MLB physical coordinates only',
            'raw_coordinates':'provider-specific; never combined across coordinate systems'},
        'policy_input_rule':'No relay_text, WPA, future outcome, current pitch measurements or season averages are pre-decision policy observations.',
        'rights_status':source['rights_status'],'credit':source['credit'],
        'limitations':['Public distribution is not independent upstream rights certification.','Shared field names do not equalize league strength, eras, balls or parks.',
            'Location categories from Japanese text remain qualitative; SPAIA pixels have not become physical coordinates.',
            'KBO post-pitch counts are reversed only when the previous count is identifiable. Missing observations are never zero-filled.']}
    write_json(folder/'manifest.json',result);return folder/'manifest.json'


def transition_between(before,after):
    """Consecutive observed pitches identify a completed PA's movement, or none.

    Missing scores, gaps, impossible conservation and mid-PA restarts are not
    silently converted into zero runs or clean outs.
    """
    if not before or not before['terminal'] or before['game']!=after['game']:return None
    if (after['balls'],after['strikes'])!=(0,0) or after['ordering']<=before['ordering']:return None
    if 'sequence' in after.keys():
        if after['game'].startswith('nextpitchh-naver-v1:'):
            if after['ordering']!=before['ordering']+1:return None
        elif after['sequence']!=1:return None
    old_half=before['inning']*2+before['bottom'];new_half=after['inning']*2+after['bottom']
    if new_half not in (old_half,old_half+1):return None
    delta=after['outs']-before['outs'] if new_half==old_half else 3-before['outs']
    end=after['bases'] if new_half==old_half else 0
    runs=before['runs']
    if runs is None and before['home_difference'] is not None and after['home_difference'] is not None:
        runs=(after['home_difference']-before['home_difference'])*(1 if before['bottom'] else -1)
    if runs is None or int(runs)!=runs or not 0<=runs<=4 or not 0<=delta<=3-before['outs']:return None
    participants=1+before['bases'].bit_count()
    if before['outs']+delta<3:
        if delta+end.bit_count()+runs!=participants:return None
    elif end!=0 or delta+runs>participants:return None
    return delta,end,int(runs)


def build_counts(root,manifests,output,*,include_retrosheet=True):
    """Small source-derived tables for training; no originals or learned weights."""
    import gzip
    root=Path(root).resolve();cohorts={};sources=[]
    for manifest in manifests:
        manifest=local_path(root,Path(manifest).resolve());meta=json.loads(manifest.read_text(encoding='utf-8'))
        database=manifest.parent/'pitches.sqlite'
        if checksum(database)!=meta['database_sha256']:raise ValueError('공통 투구 DB 지문 불일치')
        sources.append({'league':meta['league'],'signature':meta['signature'],'source_manifest_sha256':meta['source_manifest_sha256'],
            'credit':meta['credit'],'rights_status':meta['rights_status'],
            'file_sha256':[f['sha256'] for f in meta['files']]})
        db=sqlite3.connect(f'file:{database}?mode=ro',uri=True);db.row_factory=sqlite3.Row
        parts={};counts={};moves={};profiles={};players={}
        for key,info in meta['cohorts'].items():
            days=info['dates']
            if len(days)<3:continue
            a=max(1,int(len(days)*.6));b=min(len(days)-1,max(2,int(len(days)*.8)))
            parts[key]=(days[a],days[b])
            counts[key]={p:defaultdict(Counter) for p in ('fit','validation','test')}
            moves[key]={p:defaultdict(Counter) for p in ('fit','validation','test')}
            players[key]=[r[0] for r in db.execute('SELECT pitcher,COUNT(*) n FROM pitches WHERE cohort=? AND date<? AND pitcher IS NOT NULL GROUP BY pitcher ORDER BY n DESC LIMIT 3',(key,days[a]))]
            profiles[key]=defaultdict(Counter)
            cohorts[key]={'league':meta['league'],'season':int(key.split(':')[1]),'source':key.split(':',2)[2],
                'pitchers':players[key],'pitcher_names':{p:f'기록 기반 투수 {i+1}' for i,p in enumerate(players[key])},
                'source_signature':meta['signature'],'source_rows':info['rows'],'missing':info['missing'],
                'split':{'fit':[days[0],days[a-1]],'validation':[days[a],days[b-1]],'test':[days[b],days[-1]]}}
        previous=None;seen=0
        for r in db.execute('SELECT * FROM pitches ORDER BY game,ordering'):
            key=r['cohort']
            if key not in parts:previous=r;continue
            a,b=parts[key];phase='fit' if r['date']<a else 'validation' if r['date']<b else 'test'
            family=r['pitch_family'];location=r['location']
            if r['observed_action'] and r['event']:
                cell=(r['balls'],r['strikes'],r['observed_action'],family,location)
                counts[key][phase][cell][r['event']]+=1
            if phase=='fit' and r['pitcher'] in players[key] and family:profiles[key][r['pitcher']][family]+=1
            movement=transition_between(previous,r)
            if movement and previous['cohort'] in parts:
                pk=previous['cohort'];pa,pb=parts[pk]
                pp='fit' if previous['date']<pa else 'validation' if previous['date']<pb else 'test'
                # Both observations must belong to the same date split.
                if pp==phase and pk==key:
                    mk=(previous['outs'],previous['bases'],previous['terminal'],previous['observed_action']=='bunt')
                    moves[pk][pp][mk][movement]+=1
            previous=r;seen+=1
            if seen%500000==0:print(f'{meta["league"]} 학습 계수 · {seen:,}투구',flush=True)
        db.close()
        for key in parts:
            c=cohorts[key]
            c['counts']={p:[[ *cell,dict(v)] for cell,v in counter.items()] for p,counter in counts[key].items()}
            c['movements']={p:[[*cell,[[*outcome,n] for outcome,n in v.items()]] for cell,v in counter.items()] for p,counter in moves[key].items()}
            c['pitcher_repertoires']={p:dict(v) for p,v in profiles[key].items()}
            c['used_pitches']={p:sum(sum(v.values()) for v in cc.values()) for p,cc in counts[key].items()}
            c['used_movements']={p:sum(sum(v.values()) for v in cc.values()) for p,cc in moves[key].items()}
    # PBP narratives are useful running records, although not pitch rows.
    running_info={}
    for manifest in manifests:
        meta=json.loads(Path(manifest).read_text(encoding='utf-8'))
        if meta['league']!='NPB':continue
        from .corpus_running import extract
        plays,rejected=extract(root,meta);running_info={'joined_plays':len(plays),'excluded':rejected}
        for key,c in cohorts.items():
            if c['league']!='NPB':continue
            tables={p:defaultdict(Counter) for p in ('fit','validation','test')}
            for row in plays:
                # Earlier completed seasons may teach a later cohort, never vice versa.
                phase='fit' if row['date']<c['split']['validation'][0] else 'validation' if row['date']<=c['split']['validation'][1] else 'test' if row['date']<=c['split']['test'][1] else None
                if phase is None:continue
                cell=tuple(row[k] for k in ('outs','bases','balls','strikes','action'))
                tables[phase][cell][row['pitch_event'],row['outs_added'],row['end_bases'],row['runs']]+=1
            c['running']={p:[[*cell,[[*outcome,n] for outcome,n in counts.items()]] for cell,counts in cells.items()] for p,cells in tables.items()}
    ready={k:c for k,c in cohorts.items() if c['used_pitches']['fit']>=1000 and c['used_pitches']['validation']>=100 and c['used_pitches']['test']>=100 and len(c['pitchers'])==3}
    value={'schema':'multileague-pitch-counts-v1','created_at':utc_now(),'source_status':'REAL_OBSERVED',
           'cohorts':ready,'sources':sources,'running_narration':running_info,'excluded_cohorts':{k:c['used_pitches'] for k,c in cohorts.items() if k not in ready},
           'assumptions':['Executed pitch family and coarse observed region are patterns, not recorded intended catcher targets.',
               'Outcomes conditioned on observed batter actions are not identified causal intervention effects.',
               'Each league/year has its own fit and future holdouts; no MLB probability is substituted for KBO or NPB.',
               'KBO has pitch type and speed but no pitch coordinates in this release. NPB pixel coordinates remain uncalibrated.',
               'Source-derived count tables are not neural checkpoints or raw data redistribution.',
               'Native runner movements reject missing first-pitch observations and gaps in consecutive KBO pitch lines; unobserved intervening events are not inferred.']}
    if include_retrosheet:
        from .retrosheet_corpus import enrich
        value=enrich(root,value)
        ready=value['cohorts']
    from .corpus_measurements import add_measurements
    value=add_measurements(root,manifests,value)
    output=Path(output)
    if output.exists():raise FileExistsError('기존 학습 계수 덮어쓰기 금지')
    with gzip.GzipFile(filename=str(output),mode='wb',mtime=0) as f:f.write(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
    return {'sha256':checksum(output),'bytes':output.stat().st_size,'cohorts':len(ready),
            'coverage':{league:sorted({c['season'] for c in ready.values() if c['league']==league}) for league in ('MLB','KBO','NPB')}}
