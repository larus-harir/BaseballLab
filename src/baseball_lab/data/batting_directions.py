"""Recorded contact areas and handedness, never reconstructed batting intent.

Unknown/switch stance and boundary areas stay unknown. Non-contact probabilities
are not fitted from these contact-only records. No pixels become physical angles.
"""
from collections import Counter,defaultdict
from pathlib import Path
from functools import lru_cache
import csv,gzip,hashlib,json,re
from .lineage import checksum,utc_now

CONTACT=('out','single','double','triple','home_run')
AIMS=('pull','center','opposite','left','right')
SIDES={'3':'right','34':'right','4':'right','9':'right','5':'left','56':'left','6':'left','7':'left','1':'center','2':'center','8':'center'}


def handedness(value):
    return {'L':'L','R':'R','left':'L','right':'R'}.get(value,'U')


def approach(side,hand):
    if side not in ('left','center','right'):return None
    if side=='center':return 'center'
    if hand=='U':return side
    return 'pull' if side==('left' if hand=='R' else 'right') else 'opposite'


def retro_area(code):
    match=re.fullmatch(r'(\d{1,2})[A-Z+?]*',code or '')
    return SIDES.get(match[1]) if match else None


def narrative_area(text,league):
    # The recorded direction/fielder area is a coarse area, not a measured angle.
    words=(('좌익수','left'),('중견수','center'),('우익수','right'),('3루수','left'),('유격수','left'),('2루수','right'),('1루수','right'),('투수','center')) if league=='KBO' else (
        ('レフト','left'),('センター','center'),('ライト','right'),('左翼','left'),('中堅','center'),('右翼','right'),('ショート','left'),('サード','left'),('セカンド','right'),('ファースト','right'),('ピッチャー','center'))
    text=text.split(':',1)[-1].strip()
    matches=[(text.find(word),side) for word,side in words if word in text]
    return min(matches)[1] if matches else None


def contact_type(text,event=None):
    if event=='home_run':return None  # A home run is not a measured fly/line-drive classification.
    for words,kind in ((('땅볼','ゴロ'),'ground'),(('직선타','ライナー'),'line'),(('팝플라이','ポップ'),'popup'),(('플라이','フライ'),'fly')):
        if any(w in text for w in words):return kind
    return None


def compile_directions(root,output):
    from .pitch_corpus import normalized_rows
    from .pitch_normalize import npb as npb_row
    from .training_window import sources
    from baseball_lab.experiments.match.pitch_game.corpus_world import corpus,ASSET_SHA256
    from baseball_lab.experiments.match.pitch_game.research import checked_sequence
    root=Path(root).resolve();output=Path(output)
    if output.exists():raise FileExistsError('기존 타격 방향 자료를 덮어쓰지 않습니다.')
    base=corpus();cohorts=base['cohorts'];counters={k:{p:Counter() for p in ('fit','validation','test')} for k in cohorts}
    hands={k:{p:Counter() for p in ('fit','validation','test')} for k in cohorts};coverage={k:{p:Counter() for p in ('fit','validation','test')} for k in cohorts}
    lineage=[]
    def phase(key,day):return next((p for p,(lo,hi) in cohorts[key]['split'].items() if lo<=day<=hi),None)
    def add(key,day,b,s,hand,side,kind,event):
        part=phase(key,day)
        if not part:return
        h=handedness(hand);coverage[key][part]['contact_rows']+=1
        if side is None:coverage[key][part]['area_unknown']+=1
        if h=='U':coverage[key][part]['stance_unknown']+=1
        counters[key][part][b,s,h,approach(side,h),side,kind,event]+=1
    for year,source in sorted(sources(root).items()):
        key=next((k for k,c in cohorts.items() if c['league']=='MLB' and c['season']==year),None)
        if not key:continue
        entry=next(f for f in source['files'] if f['path'].endswith('.csv'));path=root/entry['path']
        if checksum(path)!=entry['sha256']:raise ValueError('MLB 타구 원본 지문 불일치')
        calendar={}
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['gametype']=='regular' and r['pbp']=='full':calendar[r['gid']]=max(calendar.get(r['gid'],''),r['date'])
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['gid'] not in calendar or r['pa']!='1' or r['gametype']!='regular' or r['pbp']!='full':continue
                d=calendar[r['gid']];day=d[:4]+'-'+d[4:6]+'-'+d[6:8];part=phase(key,day)
                if not part:continue
                hands[key][part][handedness(r['bathand'])]+=1
                if r['bip']!='1' or r['bunt']=='1' or '.' in r['pitches']:continue
                event=next((e for field,e in [('single','single'),('double','double'),('triple','triple'),('hr','home_run')] if r[field]=='1'),'out')
                seq,reason=checked_sequence({'pitches':r['pitches'],'event':event,'intentional_walk':r['iw']=='1'})
                if reason:coverage[key][part]['pitch_sequence_unusable']+=1;continue
                b,s,action,_=seq[-1]
                if action!='swing':continue
                kind={'G':'ground','F':'fly','L':'line','P':'popup'}.get(r['hittype'])
                add(key,day,b,s,r['bathand'],retro_area(r['loc']),kind,event)
        lineage.append({'league':'MLB','season':year,'sha256':entry['sha256'],'basis':'Retrosheet loc and bathand, not first fielder'})
        print('MLB '+str(year)+' 실제 타구 방향 연결',flush=True)
    for file in (root/'data/local/pitch-corpus').glob('*/manifest.json'):
        meta=json.loads(file.read_text(encoding='utf-8'))
        if meta['league'] not in ('KBO','NPB'):continue
        league=meta['league']
        for entry in meta['files']:
            if checksum(root/entry['path'])!=entry['sha256']:raise ValueError('타구 원본 지문 불일치')
        if league=='KBO':
            @lru_cache(maxsize=4)
            def originals(file_id):
                with (root/meta['files'][file_id]['path']).open(encoding='utf-8-sig',newline='') as f:return {line:r for line,r in enumerate(csv.DictReader(f),2)}
            for r,file_id,line,ordering in normalized_rows(root,meta,file.parent):
                if isinstance(r,str):continue
                key=f"KBO:{r['season']}:{r['namespace']}";part=phase(key,r['date'])
                if not part:continue
                raw=originals(file_id)[line]
                if r['balls']==0 and r['strikes']==0:hands[key][part][handedness(raw.get('batter_hit_type'))]+=1
                if r['raw_code']!='H' or r['observed_action']!='swing' or r['event'] not in CONTACT:continue
                add(key,r['date'],r['balls'],r['strikes'],raw.get('batter_hit_type'),narrative_area(raw['relay_text'],league),contact_type(raw['relay_text'],r['event']),r['event'])
        else:
            # Use only conflict-free physical pitches from the normalized release.
            import sqlite3
            db=sqlite3.connect(f'file:{file.parent/"pitches.sqlite"}?mode=ro',uri=True)
            accepted={(a,b) for a,b in db.execute('SELECT file_id,line FROM pitches')};db.close()
            for file_id,entry in enumerate(meta['files']):
                with (root/entry['path']).open(encoding='utf-8-sig',newline='') as f:
                    for line,raw in enumerate(csv.DictReader(f),2):
                        if (file_id,line) not in accepted:continue
                        r=npb_row(raw);key=f"NPB:{r['season']}:{r['namespace']}";part=phase(key,r['date'])
                        if not part:continue
                        if r['sequence']==1:hands[key][part][handedness(raw.get('batter_hand'))]+=1
                        if r['observed_action']!='swing' or r['event'] not in CONTACT:continue
                        text=raw.get('description_jap','')
                        add(key,r['date'],r['balls'],r['strikes'],raw.get('batter_hand'),narrative_area(text,league),contact_type(text,r['event']),r['event'])
        lineage.append({'league':league,'source_signature':meta['signature'],'raw_file_count':len(meta['files']),'basis':'explicit PBP narrative area; no pixel calibration; ambiguous stance remains unknown'})
        print(league+' 실제 타구 방향 연결',flush=True)
    result={'schema':'observed-batting-directions-v1','source_status':'REAL_OBSERVED','created_at':utc_now(),
        'base_asset_sha256':ASSET_SHA256,'adapter_sha256':checksum(Path(__file__)),'sources':lineage,
        'cohorts':{k:{'split':cohorts[k]['split'],'counts':{p:[[*cell,n] for cell,n in values.items()] for p,values in counters[k].items()},
            'hand_counts':{p:dict(v) for p,v in hands[k].items()},'coverage':{p:dict(v) for p,v in coverage[k].items()}} for k in cohorts},
        'assumptions':['Recorded contact direction is an outcome label, never a recorded batting intention.',
            'Directional swing is an idealized contact-area target. Swing miss/foul/contact rates are shared with the ordinary swing; target effects on those rates are unidentified.',
            'Contact outcomes conditional on area/hand/count pool native league/year records; pitch-type-by-direction intervention effects are not identified.',
            'Switch or missing batting stance is not guessed from pitcher hand. Unknown-stance environments offer left/center/right targets instead.',
            'Field areas are qualitative; infield narrative areas are not measured spray angles. Boundary location codes remain unknown.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    body=gzip.compress(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode(),mtime=0);output.write_bytes(body)
    return {'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'cohorts':len(cohorts),'fit_contacts':sum(sum(v['fit'].values()) for v in counters.values())}
