"""Lossless categorical counts with optional measured speed, not zero filling.

Fit-only, within-cohort/family quantiles define relative speed bands. Missing
pitch types still contribute to count/action outcomes. Unmapped tracking fields
remain in checksum-linked originals and are listed in the feature catalog.
"""
from collections import Counter,defaultdict
from functools import lru_cache
from pathlib import Path
import csv,json,sqlite3
from .lineage import checksum
from . import pitch_normalize as adapter


def cutpoints(histogram):
    total=sum(histogram.values());answer=[]
    if not total:return None
    for fraction in (1/3,2/3):
        seen=0
        for value,n in sorted(histogram.items()):
            seen+=n
            if seen>=fraction*total:answer.append(value);break
    return answer


def band(value,cuts):
    if value is None or cuts is None:return None
    if cuts[0]==cuts[1]:return 'middle'
    return 'slow' if value<=cuts[0] else 'fast' if value>=cuts[1] else 'middle'


def add_measurements(root,manifests,value):
    root=Path(root).resolve()
    for manifest in manifests:
        manifest=Path(manifest);meta=json.loads(manifest.read_text(encoding='utf-8'))
        database=manifest.parent/'pitches.sqlite'
        if checksum(database)!=meta['database_sha256']:raise ValueError('측정 관측 DB 지문 불일치')
        selected={k:c for k,c in value['cohorts'].items() if k in meta['cohorts']}
        db=sqlite3.connect(f'file:{database}?mode=ro',uri=True)
        lookup=sqlite3.connect(f'file:{manifest.parent/"atbats.sqlite"}?mode=ro',uri=True) if meta['league']=='MLB' else None
        @lru_cache(maxsize=2048)
        def atbat_label(key):
            row=lookup.execute('SELECT payload FROM ab WHERE id=?',(key,)).fetchone()
            return adapter.final_event(json.loads(row[0])['event']) if row else None
        @lru_cache(maxsize=8)
        def kbo_labels(file_id):
            with (root/meta['files'][file_id]['path']).open(encoding='utf-8-sig',newline='') as f:
                return {line:adapter.final_event(r.get('relay_text','')) for line,r in enumerate(csv.DictReader(f),2) if r.get('pitch_result')=='H'}
        histograms=defaultdict(Counter)
        for cohort,date,family,speed,raw_type in db.execute('SELECT cohort,date,pitch_family,speed_mps,raw_type FROM pitches WHERE speed_mps IS NOT NULL AND pitch_family IS NOT NULL'):
            if cohort not in selected or date>=selected[cohort]['split']['validation'][0] or raw_type=='FO':continue
            histograms[cohort,family][speed]+=1
        cuts={key:cutpoints(hist) for key,hist in histograms.items()}
        counters={key:{p:defaultdict(Counter) for p in c['split']} for key,c in selected.items()}
        profiles={key:defaultdict(Counter) for key in selected}
        speeds={key:defaultdict(lambda:[0,0.]) for key in selected}
        for cohort,date,b,s,a,f,l,speed,event,pitcher,raw_type,raw_code,pa,file_id,line in db.execute('SELECT cohort,date,balls,strikes,observed_action,pitch_family,location,speed_mps,event,pitcher,raw_type,raw_code,pa,file_id,line FROM pitches'):
            if meta['league']=='MLB' and (raw_code=='I' or raw_type=='IN'):continue
            if meta['league']=='MLB' and raw_code in ('X','D','E'):event=atbat_label(pa.rsplit(':',1)[-1])
            if meta['league']=='KBO' and raw_code=='H':event=kbo_labels(file_id).get(line)
            if cohort not in selected or not a or not event:continue
            c=selected[cohort];phase='fit' if date<c['split']['validation'][0] else 'validation' if date<c['split']['test'][0] else 'test'
            # Publisher documentation calls rare FO a pitchout. Do not silently
            # relabel that ambiguous legacy code as a forkball/splitter.
            if raw_type=='FO':f=None
            speed_band=band(speed,cuts.get((cohort,f))) if f else None
            counters[cohort][phase][b,s,a,f,l,speed_band][event]+=1
            if phase=='fit':
                if pitcher in c['pitchers'] and f:profiles[cohort][pitcher][f+'|'+(speed_band or 'missing')]+=1
                if f and speed is not None:
                    z=speeds[cohort][f];z[0]+=1;z[1]+=speed
        db.close()
        if lookup:lookup.close()
        for key,c in selected.items():
            if meta['league'] in ('KBO','NPB'):c['movement_link_rule']='Next observed PA must begin at its first pitch; KBO file lines must be adjacent, with identifiable scores and participant conservation.'
            c['counts']={p:[[*cell,dict(counts)] for cell,counts in cells.items()] for p,cells in counters[key].items()}
            c['used_pitches']={p:sum(sum(n.values()) for n in cells.values()) for p,cells in counters[key].items()}
            c['speed_cutpoints_mps']={family:values for (cohort,family),values in cuts.items() if cohort==key}
            c['speed_fit_summary']={family:{'observed':n,'mean_mps':total/n} for family,(n,total) in speeds[key].items()}
            c['pitcher_speed_repertoires']={p:dict(n) for p,n in profiles[key].items()}
            c['pitcher_repertoires']={p:dict(Counter({family:sum(n for key,n in counts.items() if key.split('|')[0]==family) for family in {key.split('|')[0] for key in counts}})) for p,counts in profiles[key].items()}
        if meta['league']=='KBO':
            # Recompute native movements with terminal-only, corrected PA labels.
            from .pitch_corpus import normalized_rows,transition_between
            native={key:{p:defaultdict(Counter) for p in c['split']} for key,c in selected.items()}
            previous=None
            for row,file_id,line,ordering in normalized_rows(root,meta,manifest.parent):
                if isinstance(row,str):continue
                row['ordering']=ordering;key=f"KBO:{row['season']}:{row['namespace']}"
                movement=transition_between(previous,row)
                if movement:
                    pk=f"KBO:{previous['season']}:{previous['namespace']}"
                    if pk in selected and pk==key:
                        c=selected[pk];phase=next((p for p,(lo,hi) in c['split'].items() if lo<=previous['date']<=row['date']<=hi),None)
                        if phase:native[pk][phase][previous['outs'],previous['bases'],previous['terminal'],previous['observed_action']=='bunt'][movement]+=1
                previous=row
            for key,c in selected.items():
                c['movements']={p:[[*cell,[[*outcome,n] for outcome,n in counts.items()]] for cell,counts in cells.items()] for p,cells in native[key].items()}
                c['used_movements']={p:sum(sum(n.values()) for n in cells.values()) for p,cells in native[key].items()}
        headers=set()
        for item in meta['files']:
            with (root/item['path']).open(encoding='utf-8-sig',newline='') as f:headers.update(next(csv.reader(f)))
        for source in value['sources']:
            if source.get('signature')!=meta['signature']:continue
            source['raw_field_catalog']=sorted(headers)
            source['target_adapter_sha256']=checksum(Path(adapter.__file__))
            source['movement_adapter_sha256']=checksum(Path(__file__).with_name('pitch_corpus.py'))
            source['normalization_quality']={'raw_rows':meta['raw_rows'],'retained_rows':meta['normalized_rows'],
                'excluded':meta['excluded'],'exact_duplicates':meta['exact_duplicates'],
                'conflicting_ids':meta['conflicting_ids_quarantined'],
                'quarantined_rows':meta['raw_rows']-meta['normalized_rows']-sum(meta['excluded'].values())-meta['exact_duplicates'],
                'optional_field_inspection_scope':'first accepted observations before late ID conflicts are quarantined; retained model counts are recomputed from the conflict-free database'}
            source['policy_excluded_fields']=['relay_text','reward_wpa','pitcher_vs_batter_avg','batter_recent_avg','home_final_score','away_final_score']
            if meta['league']=='KBO':
                context=manifest.parent/'game_index.csv'
                source['regular_season_evidence']={'url':'https://raw.githubusercontent.com/NextPitchh/KBO_Crawler/18a5810d188c81f989499844ef525dbb594a29d1/data/game_ids/game_index.csv','sha256':checksum(context)}
        print(meta['league']+' 측정 구속대·결측 관측 연결 완료',flush=True)
    value['schema']='multileague-pitch-counts-v2'
    value['assumptions'].extend(['Relative speed bands use only fit-period within-family measured-speed quantiles, not manual player ratings.',
        'Unknown optional pitch type, speed or location never removes an otherwise known count/action/outcome.',
        'Unmapped optional tracking fields remain in hash-linked originals; the feature catalog is not a claim those fields affect this model.'])
    value['assumptions'].append('Intentional balls are retained as observations but excluded from normal-pitch outcome fitting; intentional walks are explicit rule-based defense actions.')
    return value
