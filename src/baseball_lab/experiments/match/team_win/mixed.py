"""Common-policy league mixtures over observed MLB transitions.

League PA marginals change donor sampling weights. They never fabricate KBO
or NPB runner transitions. This is a versioned transport assumption, not a
claim of validated league-strength conversion or real cross-league games.
"""
import csv
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
from baseball_lab.data.lineage import checksum,content_hash
from baseball_lab.data.warehouse import local_path
from baseball_lab.data.community import integer
from baseball_lab.matchup import shared
from baseball_lab.r1.environment import Observation,PITCH_ACTIONS,key,fit

LEAGUES=('MLB','KBO','NPB')
EVENTS=tuple(shared.LABELS)
VERSION='league-mixture-observed-transition-v1'


def weights(value):
    if not isinstance(value,dict) or not value or set(value)-set(LEAGUES):raise ValueError('학습할 리그를 하나 이상 선택하세요.')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in value.values()):raise ValueError('선택한 리그의 비중은 양의 유한값이어야 합니다.')
    total=sum(value.values())
    if not math.isfinite(total):raise ValueError('리그 비중의 합계를 확인하세요.')
    result={l:value[l]/total for l in LEAGUES if l in value}
    if any(v<=0 for v in result.values()):raise ValueError('리그 비중 차이가 너무 큽니다.')
    return result


def validate(root,value):
    chosen=weights(value);names=set()
    for p in (Path(root)/'data/local/collections').glob('*/manifest.json'):
        local_path(root,p);m=json.loads(p.read_text(encoding='utf-8'));names.add(m.get('source_namespace'))
    for league,provider in (('KBO','kaggle-netsong-kbo'),('NPB','armstjc-npb-spaia')):
        if league in chosen and provider not in names:
            from baseball_lab.data.compact import players
            if not any(r['source_namespace']==provider for r in players()):raise ValueError(f'{league}의 등록된 수집 기록이 없습니다.')
    return chosen


def rates(counts):
    if set(counts)!=set(EVENTS) or any(type(n) is not int or n<0 for n in counts.values()) or sum(counts.values())<=0:raise ValueError('공통 타석 계수·분모가 부족합니다.')
    if any(n==0 for n in counts.values()):raise ValueError('선택 리그에서 공통 사건의 표본이 부족합니다.')
    n=sum(counts.values());return {k:v/n for k,v in counts.items()}


def outcome_labels(root,dataset):
    from baseball_lab.data.training_window import sources
    from baseball_lab.matchup.outcome_details import classify
    if dataset['manifest'].get('storage_mode')=='memory-only':
        result={r['record_id']:r['common_event'] for r in dataset['records']}
        if any(e not in (*EVENTS,'non_pa') for e in result.values()):raise ValueError('공통 사건이 등록 범위를 벗어났습니다.')
        return result
    lookup={};source=sources(root)
    for year in dataset['manifest']['selected_seasons']:
        entry=next(x for x in source[year]['files'] if x['path'].endswith('.csv'));path=local_path(root,Path(root).resolve()/entry['path'])
        if checksum(path)!=entry['sha256']:raise ValueError('공통 전이의 원본 해시가 다릅니다.')
        with path.open(encoding='utf-8-sig',newline='') as f:
            for line,r in enumerate(csv.DictReader(f),2):
                if r['gametype']!='regular' or r['pbp']!='full' or r['pa']!='1':continue
                classify(r)
                event='strikeout' if r['k']=='1' else 'walk' if r['walk']=='1' else 'hit' if any(r[k]=='1' for k in ('single','double','triple','hr')) else 'other'
                lookup[f"{r['gid']}:play{r['pn']}:csvline{line}"]=event
    result={}
    for r in dataset['records']:
        event=lookup.get(r['source_row_ids'][-1])
        if event is None and not r['truncated']:raise ValueError('완료 타석 전이와 원본 사건을 연결하지 못했습니다.')
        result[r['record_id']]=event or 'non_pa'
    return result


def npb_before(root,cutoff,*,by_day=False):
    """Only known regular-season games dated before validation begins."""
    root=Path(root).resolve();files=sorted((root/'data/local/community/npb-armstjc').glob('*/manifest.json'),reverse=True)
    if not files:
        from baseball_lab.data.compact import npb_before as compact_npb
        return compact_npb(cutoff)
    local_path(root,files[0]);meta=json.loads(files[0].read_text(encoding='utf-8'));games={};hashes=[]
    for item in meta['files']:
        if item.get('kind')!='pbp':continue
        path=local_path(root,root/item['path'])
        if checksum(path)!=item['sha256']:raise ValueError('NPB 원본 검증값이 다릅니다.')
        hashes.append(item['sha256'])
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if {'1':'セ・リーグ公式戦','2':'パ・リーグ公式戦','26':'セ・パ交流戦'}.get(r['game_type_id'])!=r['game_type_name']:continue
                games[r['game_id']]=max(games.get(r['game_id'],''),r['game_date'][:10])
    c=Counter(dict.fromkeys(EVENTS,0));seen=set();dates=set();daily=defaultdict(Counter)
    for item in meta['files']:
        if item.get('kind')!='game_stats':continue
        path=local_path(root,root/item['path'])
        if checksum(path)!=item['sha256']:raise ValueError('NPB 선수 경기 원본 검증값이 다릅니다.')
        hashes.append(item['sha256'])
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                day=games.get(r['game_id'])
                if not day or day>=cutoff or r['game_date'][:10]>=cutoff or not r.get('batting_PA'):continue
                identity=(r['game_id'],r['player_id'],r['team_id'])
                if identity in seen:raise ValueError('NPB 경기별 타격 행이 중복됐습니다.')
                seen.add(identity)
                values={k:integer(r.get('batting_'+k)) for k in ('PA','SO','BB','H')}
                if any(v is None for v in values.values()):continue
                part=shared.partition({'role':'batter','counts':values})
                if part:
                    c.update(part);dates.add(day);daily[day].update(part)
    if not sum(c.values()):raise ValueError('검사 시작 전 NPB 정규시즌 관측이 없습니다. NPB를 포함하려면 2025년 수집 기간을 권장합니다.')
    if by_day:return {'daily_counts':dict(daily),'source_hashes':hashes,'rights_status':meta['rights_status'],'attribution':meta['license']['attribution']}
    q=rates(dict(c))
    return {'rates':q,'counts':dict(c),'dates':[min(dates),max(dates)],'cutoff_exclusive':cutoff,
        'provider':'armstjc-npb-spaia','source_hashes':hashes,'rights_status':meta['rights_status'],
        'date_semantics':'provider game_date; historical publication/correction availability is not independently verified',
        'attribution':meta['license']['attribution'],'scope':'Only observed regular-season batting games before validation; no NPB runner-transition claim.'}


def targets(root,chosen,cutoff,fit_rows,labels):
    c=Counter(dict.fromkeys(EVENTS,0))
    for r in fit_rows:
        label=labels[r['record_id']]
        if label in EVENTS:c[label]+=1
    reference=rates(dict(c));result={}
    if 'MLB' in chosen:result['MLB']={'rates':reference,'counts':dict(c),'dates':[min(r['date'] for r in fit_rows),max(r['date'] for r in fit_rows)],'provider':'retrosheet-fit-only'}
    if 'KBO' in chosen:
        data=shared.catalog(root);year=max((int(k.split(':')[1]) for k,v in data['baselines'].items() if k.startswith('KBO:') and int(k.split(':')[1])<int(cutoff[:4])),default=None)
        if year is None:raise ValueError('검사 시작 전 완료된 KBO 시즌 자료가 없습니다.')
        b=data['baselines'][f'KBO:{year}'];rates(b['counts'])
        result['KBO']={'rates':b['rates'],'counts':b['counts'],'dates':[f'{year}-01-01',f'{year}-12-31'],
            'provider':b['source_namespace'],'dataset_id':data['dataset_id'],'scope':'Latest completed prior season; current/future season aggregates excluded.'}
    if 'NPB' in chosen:result['NPB']=npb_before(root,cutoff)
    return reference,result


class Environment:
    def __init__(self,base,labels,reference,calibration,mixture):
        self.base=base;self.labels=labels;self.reference=reference;self.calibration=calibration;self.mixture=weights(mixture)
        self.legal=base.legal;self.cells=base.cells;self.name=base.name;self.active_league=next(iter(self.mixture));self.episode_counts=Counter()
        self.grouped={};self.distributions={}
        for cell,rows in base.cells.items():
            groups=defaultdict(list)
            for row in rows:groups[labels[row['record_id']]].append(row)
            self.grouped[cell]=dict(groups)
            for league in self.mixture:
                q=calibration[league]['rates']
                masses={k:len(v)*(q[k]/reference[k] if k in EVENTS else 1.) for k,v in groups.items()};total=sum(masses.values())
                self.distributions[(league,cell)]={k:v/total for k,v in masses.items()}
        self.model_id=content_hash({'base':base.model_id,'version':VERSION,'reference':reference,'calibration':calibration,'mixture':self.mixture})

    def begin(self,rng):
        self.active_league=rng.choices(tuple(self.mixture),weights=tuple(self.mixture.values()),k=1)[0];self.episode_counts[self.active_league]+=1

    def batter_actions(self,obs):return self.base.batter_actions(obs)

    def step(self,obs,batter_action,pitcher_action,rng):
        if batter_action not in self.batter_actions(obs) or pitcher_action not in PITCH_ACTIONS:raise ValueError('지원하지 않는 행동입니다.')
        league=self.active_league
        if pitcher_action=='intentional_walk':
            nxt,runs,evidence=self.base.step(obs,batter_action,pitcher_action,rng)
            return nxt,runs,{**evidence,'environment_league':league,'donor_league':'RULE'}
        cell=key(obs.outs,obs.bases,batter_action);q=self.distributions[(league,cell)]
        event=rng.choices(tuple(q),weights=tuple(q.values()),k=1)[0];row=rng.choice(self.grouped[cell][event])
        return Observation(obs.outs+row['outs_added'],row['end_bases']),row['runs'],{
            'source_status':'MODEL_TRANSPORT_ASSUMPTION','environment_league':league,'donor_league':'MLB',
            'donor_record_id':row['record_id'],'donor_game_id':row['game_id'],'donor_event_codes':row['event_codes'],
            'coarse_event':event,'note':'Observed MLB transition, sampled with a league-marginal weight; not an observed KBO/NPB play.'}

    def serialize(self):
        return {'model_id':self.model_id,'base_model_id':self.base.model_id,'version':VERSION,'mixture':self.mixture,
            'calibration':self.calibration,'reference_fit_only':self.reference,
            'conditional_event_distributions':{l:{cell:self.distributions[(l,cell)] for cell in self.cells} for l in self.mixture}}

    def for_league(self,league):return Environment(self.base,self.labels,self.reference,self.calibration,{league:1})

    def bunt_effect_ablation(self):return Environment(self.base.bunt_effect_ablation(),self.labels,self.reference,self.calibration,self.mixture)


def train(root,dataset,start,end,output,config,mixture,*,test_only=False,prepared_labels=None,prepared_targets=None):
    from .half_inning import train as train_inning
    if dataset['manifest']['source_status']!='REAL_OBSERVED' and not test_only:raise ValueError('실제 원천 자료만 연구 학습에 사용합니다.')
    chosen=weights(mixture);envs,model=fit(dataset,start,end)
    labels=prepared_labels if test_only and prepared_labels is not None else outcome_labels(root,dataset)
    fit_rows=[r for r in dataset['records'] if model['split']['fit']['dates'][0]<=r['date']<=model['split']['fit']['dates'][1]]
    cutoff=model['split']['validation']['dates'][0]
    if test_only and prepared_targets is not None:reference,calibration=prepared_targets
    else:reference,calibration=targets(root,chosen,cutoff,fit_rows,labels)
    plan={'version':VERSION,'weights':chosen,'reference_fit_only':reference,'calibration':calibration,
        'calibration_cutoff_exclusive':cutoff,'league_identity_observed_by_policy':False,
        'transition_donor_league':'MLB','scope':'One common policy learns across weighted league environments; conditional MLB runner transitions are assumed transferable, not empirically verified for KBO/NPB.',
        'weighting':'league marginal / fit-only MLB marginal, normalized within observed state/action cells; missing outcomes are never invented',
        'limitations':['No absolute league strength conversion.','IBB separation is incomplete in some league totals; this is marginal scenario reweighting, not an identified challenge/bunt effect.',
            'Source-date splitting is retrospective; it is not proof that the downloaded revision was publicly available at each historical date.',
            'Prior KBO seasons and partial observed NPB fit-period games have different temporal coverage; source dates are retained.',
            'Final evaluation uses held-out MLB donors with frozen fit-period calibration; it is not independent predictive validation on KBO/NPB transitions.']}
    model={**model,'mixture':plan,'base_dataset_id':model['dataset_id'],'dataset_id':content_hash({'base':model['dataset_id'],'mixture':plan})}
    wrapped={k:Environment(e,labels,reference,calibration,chosen) for k,e in envs.items()}
    adapted={'records':dataset['records'],'manifest':{**dataset['manifest'],'base_dataset_id':dataset['manifest']['dataset_id'],'dataset_id':model['dataset_id'],'league_mixture':plan}}
    return train_inning(adapted,start,end,output,config,test_only=test_only,evidence={'league_mixture':plan},prepared=(wrapped,model))
