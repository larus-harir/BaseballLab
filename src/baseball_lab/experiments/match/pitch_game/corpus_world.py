"""One policy can learn across observed league/year pitch-pattern worlds.

Patterns are observed pitch families/regions, not measured catcher targets.
Every cohort retains its own fit, holdout and native runner distributions.
"""
from collections import Counter,defaultdict
from dataclasses import replace
from functools import lru_cache
from importlib.resources import files
import gzip,hashlib,json,math
from itertools import permutations
import numpy as np
from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.r1.data import walk
from .research import OFF,DEF,EVENTS,FEATURES,Observation,features as original_features

ASSET='pitch-corpus-counts-v2.json.gz'
ASSET_SHA256='c3f5ddab9e8656f305690544510d732b850c35bcdd8b8af6a82a308f4ff53f13'
OBS_SCHEMA='multileague-pitch-observation-v3'
ACTION_SCHEMA='observed-pitch-and-contact-patterns-v3'
FAMILY_CUES=('fastball','sinker','cutter','slider','curve','changeup','splitter','knuckle')
LOCATION_CUES=tuple(h+'_'+v for h in ('inside','middle','outside') for v in ('low','middle','high'))


@lru_cache(maxsize=1)
def corpus():
    body=files('baseball_lab').joinpath('data','resources',ASSET).read_bytes()
    if hashlib.sha256(body).hexdigest()!=ASSET_SHA256:raise ValueError('공통 투구 학습 자료 지문이 다릅니다.')
    value=json.loads(gzip.decompress(body))
    if value['schema']!='multileague-pitch-counts-v2' or value['source_status']!='REAL_OBSERVED':raise ValueError('실제 공통 투구 자료만 사용합니다.')
    return value


def inventory():
    return {'schema':'pitch-training-inventory-v1','cohorts':[
        {'id':key,'league':c['league'],'season':c['season'],'rows':c['source_rows'],
         'fit_pitches':c['used_pitches']['fit'],'native_movements':c['used_movements']['fit'],
         'location':'타격 방향·카운트·주루 (구종·코스 미수집)' if c['source']=='retrosheet' else '구종·구속·타구 구역 (코스 미수집)' if c['league']=='KBO' else '구종·기록상 구역·타구 방향 (화면 좌표는 별도 보존)' if c['league']=='NPB' else '구종·통과 구역·구속'}
        for key,c in corpus()['cohorts'].items()],
        'bytes':files('baseball_lab').joinpath('data','resources',ASSET).stat().st_size}


def features(o,role):
    return np.concatenate((original_features(o,role),[float(o.league==l) for l in ('MLB','KBO','NPB')],[(o.season-2000)/50],
        [float(o.pitch_family_cue==f) for f in FAMILY_CUES],[float(o.location_cue==r) for r in LOCATION_CUES],[float(o.speed_cue==v) for v in ('slow','middle','fast')],[float(o.bat_hand==h) for h in ('L','R')]))


def pattern(family,location,speed=None):return 'pitch:'+family+':'+(location or 'any')+':'+(speed or 'missing')


def legal_movement(outs,bases,event,delta,end,runs):
    starts=[0,*[i for i in (1,2,3) if bases&(1<<(i-1))]]
    if delta<0 or delta>3-outs or runs<0:return False
    if outs+delta==3:return end==0 and delta+runs<=len(starts)
    destinations=[*[i for i in (1,2,3) if end&(1<<(i-1))],*[4]*runs,*[-1]*delta]
    if len(destinations)!=len(starts):return False
    minimum={'single':1,'double':2,'triple':3}.get(event,1)
    for assignment in set(permutations(destinations)):
        if assignment[0]!=-1 and assignment[0]<minimum:continue
        if any(dest!=-1 and dest<start for start,dest in zip(starts,assignment)):continue
        if any(a!=-1 and b!=-1 and a>=b and b!=4 for i,a in enumerate(assignment) for b in assignment[i+1:]):continue
        return True
    return False


class Cohort:
    def __init__(self,value,*,validation=None):
        self.value=value;self.counts={};self.base={};self.pooled={};self.by_action={}
        for part,rows in value['counts'].items():
            fine=defaultdict(Counter);base=defaultdict(Counter);pooled=defaultdict(Counter)
            for row in rows:
                b,s,action,family,location=row[:5];speed=row[5] if len(row)==7 else None;counts=row[-1]
                fine[b,s,action,family,location,speed].update(counts);base[b,s,action].update(counts);pooled[action].update(counts)
            self.counts[part]=fine;self.base[part]=base;self.pooled[part]=pooled
        self.moves={};self.move_pool={};self.invalid_fit_movements=0
        for part,rows in value['movements'].items():
            exact=defaultdict(Counter);pooled=defaultdict(Counter)
            for outs,bases,event,bunt,values in rows:
                counts=Counter({tuple(v[:3]):v[3] for v in values})
                if part=='fit' and event in ('out','single','double','triple'):
                    valid=Counter({target:n for target,n in counts.items() if legal_movement(outs,bases,event,*target)})
                    self.invalid_fit_movements+=sum(counts.values())-sum(valid.values());counts=valid
                exact[outs,bases,event,bunt].update(counts);pooled[event,bunt].update(counts)
            self.moves[part]=exact;self.move_pool[part]=pooled
        # Shrink observed pattern cells toward a fit-only count/action model.
        # Only validation chooses strength; the final test never selects it.
        if validation is None:
            options=[0,10,50,200,None]
            candidates=[(self.check('validation',strength)['brier'],strength) for strength in options]
            self.strength=min(candidates,key=lambda v:(v[0],v[1] is not None))[1]
            self.metrics={p:self.check(p,self.strength) for p in ('validation','test')}
            self.movement_metrics={p:self.check_movements(p) for p in ('validation','test')}
        else:
            self.strength=validation['strength'];self.metrics=validation['metrics'];self.movement_metrics=validation['movement_metrics']
        families={key[3:] for key in self.counts['fit'] if key[3]}
        self.patterns={pattern(f,l,v):(f,l,v) for f,l,v in families}
        self.arrivals=defaultdict(Counter)
        for (b,s,a,f,l,v),counts in self.counts['fit'].items():self.arrivals[b,s][f,l,v]+=sum(counts.values())
        self.running={p:{tuple(row[:5]):Counter({tuple(v[:4]):v[4] for v in row[5]}) for row in rows} for p,rows in value.get('running',{}).items()}
        self.running_metrics=validation['running_metrics'] if validation is not None else {p:self.check_running(p) for p in ('validation','test')}

    def probabilities(self,b,s,action,family=None,location=None,strength=None,*,speed=None):
        base=self.base['fit'].get((b,s,action)) or self.pooled['fit'].get(action,Counter())
        total=sum(base.values())
        if not total:raise ValueError('해당 공격 선택의 실제 표본이 없습니다.')
        p={event:base[event]/total for event in EVENTS}
        counts=self.counts['fit'].get((b,s,action,family,location,speed),Counter());n=sum(counts.values())
        if family is None or strength is None or not n:return p
        return {event:(counts[event]+strength*p[event])/(n+strength) for event in EVENTS}

    def check(self,part,strength):
        count=0;loss=brier=baseline=0.
        for (b,s,action,family,location,speed),observed in self.counts[part].items():
            try:q=self.probabilities(b,s,action,family,location,strength,speed=speed);base=self.probabilities(b,s,action)
            except ValueError:continue
            for event,n in observed.items():
                count+=n;loss-=n*math.log(max(q.get(event,0),1e-12))
                brier+=n*(sum(v*v for v in q.values())-2*q.get(event,0)+1)
                baseline+=n*(sum(v*v for v in base.values())-2*base.get(event,0)+1)
        if not count:raise ValueError('공통 투구 모델의 독립 검사 표본이 없습니다.')
        return {'pitches':count,'log_loss':loss/count,'brier':brier/count,'baseline_brier':baseline/count}

    @lru_cache(maxsize=512)
    def movement(self,outs,bases,event,bunt=False):
        exact=self.moves['fit'].get((outs,bases,event,bunt))
        if exact:return exact,'same league/year/base/out/event'
        # A declared within-cohort backoff, constrained by participant conservation.
        valid=Counter()
        for (delta,end,runs),n in self.move_pool['fit'].get((event,bunt),{}).items():
            if not legal_movement(outs,bases,event,delta,end,runs):continue
            valid[delta,end,runs]=n
        if not valid and bunt:
            counts,_=self.movement(outs,bases,event,False)
            return counts,'sparse bunt advancement pooled with same league/year/terminal event'
        if not valid:raise ValueError(f'{self.value["league"]} {self.value["season"]}의 해당 진루 결과를 추정할 실제 표본이 없습니다.')
        return valid,'same league/year/event with rule-constrained base/out pooling'

    def check_running(self,part):
        total=covered=0;loss=brier=0.
        for cell,observed in self.running.get(part,{}).items():
            total+=sum(observed.values());counts=self.running.get('fit',{}).get(cell,Counter())
            denominator=sum(counts.values())
            if denominator<10:continue
            norm=sum((v/denominator)**2 for v in counts.values())
            for target,n in observed.items():
                p=counts.get(target,0)/denominator;covered+=n
                loss-=n*math.log(max(p,1e-12));brier+=n*(norm-2*p+1)
        return {'source_plays':total,'covered_plays':covered,'log_loss':loss/covered if covered else None,'brier':brier/covered if covered else None}

    def check_movements(self,part):
        total=covered=0;loss=brier=0.
        for (outs,bases,event,bunt),observed in self.moves[part].items():
            n=sum(observed.values());total+=n
            if event in ('walk','hbp'):
                end,runs=walk(bases);counts=Counter({(0,end,runs):1})
            elif event=='strikeout':counts=Counter({(1,bases if outs<2 else 0,0):1})
            elif event=='home_run':counts=Counter({(0,0,1+bases.bit_count()):1})
            else:
                try:counts,_=self.movement(outs,bases,event,bunt)
                except ValueError:continue
            denominator=sum(counts.values());norm=sum((v/denominator)**2 for v in counts.values())
            for target,amount in observed.items():
                p=counts.get(target,0)/denominator;covered+=amount
                loss-=amount*math.log(max(p,1e-12));brier+=amount*(norm-2*p+1)
        return {'observed_movements':total,'covered_movements':covered,'log_loss':loss/covered if covered else None,'brier':brier/covered if covered else None}


class CorpusWorld:
    def __init__(self,leagues=None,seasons=None,*,dataset=None,contact_data=None,validation_data=None):
        raw=dataset or corpus();leagues=leagues or ['MLB','KBO','NPB']
        if set(leagues)-{'MLB','KBO','NPB'}:raise ValueError('학습할 리그를 확인하세요.')
        selected={k:v for k,v in raw['cohorts'].items() if v['league'] in leagues and (not seasons or v['season'] in seasons)}
        if not selected:raise ValueError('선택한 리그·연도에 실제 투구 자료가 없습니다.')
        from .directional_contact import directions,ContactModel,ASSET_SHA256 as CONTACT_SHA
        contact=contact_data or directions()
        asset_sha=raw.get('_asset_sha256',ASSET_SHA256)
        if contact['base_asset_sha256']!=asset_sha:raise ValueError('투구·타구 자료 버전이 맞지 않습니다.')
        self.contacts={k:ContactModel(contact['cohorts'][k],validation=validation_data[k]['contact'] if validation_data else None) for k in selected}
        self.track_strategy=True;self.bat_hand='U';self.last_contact=None
        self.cohorts={k:Cohort(v,validation=validation_data[k]['pitch'] if validation_data else None) for k,v in selected.items()}
        self.offense_actions=tuple(dict.fromkeys((*OFF,*('swing:'+a for a in ('pull','center','opposite','left','right')),*(key[-1] for c in self.cohorts.values() for key in c.running.get('fit',{})))))
        self.defense_actions=tuple(dict.fromkeys((*DEF,*(a for c in self.cohorts.values() for a in c.patterns))))
        self.evidence={'corpus':True,'model':'multileague-pitch-contact-world-v3','asset_sha256':asset_sha,
            'batting_model':'One shared offense policy per team; virtual PA stance is sampled from fit-only reported stance frequencies. No named batter identity or player ability is assigned.',
            'contact_asset_sha256':contact.get('_asset_sha256',CONTACT_SHA),'contact_assumptions':contact['assumptions'],
            'contact_coverage':{k:m.value['coverage'] for k,m in self.contacts.items()},
            'contact_holdout':{k:m.metrics for k,m in self.contacts.items()},
            'pitcher_names':{pid:name for c in selected.values() for pid,name in c['pitcher_names'].items()},
            'cohorts':[{**{k:v[k] for k in ('league','season','source','source_rows','used_pitches','used_movements','split')},'speed_fit_summary':v.get('speed_fit_summary',{}),'speed_cutpoints_mps':v.get('speed_cutpoints_mps',{}),
                        'shrinkage':self.cohorts[key].strength} for key,v in selected.items()],
            'sources':raw['sources'],'assumptions':raw['assumptions'],
            'holdout_prediction':{part:{key:(sum(c.metrics[part][key]*c.metrics[part]['pitches'] for c in self.cohorts.values())/sum(c.metrics[part]['pitches'] for c in self.cohorts.values()) if key!='pitches' else sum(c.metrics[part]['pitches'] for c in self.cohorts.values())) for key in ('pitches','brier','baseline_brier','log_loss')} for part in ('validation','test')},
            'native_movement_holdout':{key:c.movement_metrics for key,c in self.cohorts.items()},
            'invalid_fit_movement_observations_excluded':{key:c.invalid_fit_movements for key,c in self.cohorts.items() if c.invalid_fit_movements},
            'running_holdout':{key:c.running_metrics for key,c in self.cohorts.items()},
               'roster_model':'Three fit-only observed pitcher repertoires per cohort; event probabilities pool pitchers conditional on the selected pattern. No individual ability effect is claimed.',
               'perception_model':'Idealized coarse incoming-pitch pattern cue. Not a measured human reaction model, not an intended catcher target.',
               'running_model':'Explicit observed running narration and joint next-pitch count/state. Pitch-pattern effects on steals remain pooled, not identified.',
               'rules':'Shared E01 nine-inning rules, extra runner on second, walkoff and safety limits; not a reconstruction of each historical league ruleset.',
               'transition_backoff':'Within-cohort event/base/out pooling enforces conservation, no backwards movement and no passing. Sparse bunt advancement may pool same-event ordinary contact movements.',
               'initial_policy':'Uniform legal-action exploration through zero initial output logits; no target baseball strategy.',
               'evaluation_sampling':'Choice-focused checkpoints compare identical-state policy probabilities and record executed training behavior; no ranking tournament. Explicit legacy evaluator, if called separately, covers each cohort home/away. Training cycles randomly permute selected cohorts without replacement.'}
        self.visits=Counter();self.begin_game(0)

    def begin_game(self,seed):
        from random import Random
        self.key=getattr(self,'requested_context',None) or Random(seed).choice(sorted(self.cohorts));self.requested_context=None;self.current=self.cohorts[self.key]
        v=self.current.value;self.league=v['league'];self.season=v['season'];self.pitchers=v['pitchers'];self.visits[self.key]+=1

    def begin_pa(self,rng):
        counts=self.contacts[self.key].value['hand_counts']['fit']
        self.bat_hand=rng.choices(tuple(counts),weights=tuple(counts.values()),k=1)[0] if counts else 'U'

    def training_context(self,seed,episode):
        from random import Random
        keys=sorted(self.cohorts);rng=Random(seed+((episode-1)//len(keys))*100003);rng.shuffle(keys)
        return keys[(episode-1)%len(keys)]

    def evaluation_contexts(self,n):
        keys=sorted(self.cohorts);n=max(n,2*len(keys));n+=n%2
        return [keys[(i//2)%len(keys)] for i in range(n)]

    def new_team(self,seed):
        team=tuple(NeuralPolicy(role,seed+i,actions=self.offense_actions if role=='batter' else self.defense_actions,
            feature_encoder=features,feature_names=(*FEATURES,'MLB','KBO','NPB','season',*('cue_'+f for f in FAMILY_CUES),*('cue_'+r for r in LOCATION_CUES),'cue_slow','cue_middle_speed','cue_fast','bat_left','bat_right'),
            observation_schema=OBS_SCHEMA,action_schema=ACTION_SCHEMA) for i,role in enumerate(('batter','pitcher')))
        # Broad, masked action spaces should not start with arbitrary large
        # advantages for one legal action. Zero logits give uniform exploration;
        # no baseball strategy or empirical human action frequency is a target.
        for agent in team:agent.params[-2].fill(0.)
        return team

    def legal(self,o):
        legal=['take','swing',*self.contacts[self.key].legal(o.balls,o.strikes,o.bat_hand or 'U')]
        # No optimistic bunt-only-contact model for providers without known misses.
        if self.league=='MLB' and sum(self.current.base['fit'].get((o.balls,o.strikes,'bunt'),{}).values())>=10:
            try:
                for e in ('out','single'):self.current.movement(o.outs,o.bases,e,True)
                legal.append('bunt')
            except ValueError:pass
        for key,counts in self.current.running.get('fit',{}).items():
            if key[:4]==(o.outs,o.bases,o.balls,o.strikes) and sum(counts.values())>=10:legal.append(key[-1])
        return tuple(legal)

    def defense_legal(self,o):
        actions=['pitch','intentional_walk']
        repertoire=self.current.value['pitcher_repertoires'].get(self.pitchers[o.pitcher],{})
        for name,(family,location,speed) in self.current.patterns.items():
            if repertoire.get(family,0)<10:continue
            if speed is not None and self.current.value.get('pitcher_speed_repertoires',{}).get(self.pitchers[o.pitcher],{}).get(family+'|'+speed,0)<10:continue
            if all(sum(self.current.counts['fit'].get((o.balls,o.strikes,a,family,location,speed),{}).values())>=10 for a in ('take','swing')):actions.append(name)
        return actions

    def prepare(self,o,defense,rng):
        selected=self.current.patterns.get(defense)
        if selected is None:
            arrivals=self.current.arrivals[o.balls,o.strikes]
            if not arrivals:
                arrivals=Counter()
                for cells in self.current.arrivals.values():arrivals.update(cells)
            selected=rng.choices(tuple(arrivals),weights=tuple(arrivals.values()),k=1)[0]
        self.pending_pattern=selected;self.last_contact=None
        return replace(o,pitch_family_cue=selected[0],location_cue=selected[1] or '',speed_cue=selected[2] or '')

    def pitch_probabilities(self,b,s,action,*,hand=None,selected=None):
        from baseball_lab.data.batting_directions import CONTACT
        family,location,speed=selected or self.pending_pattern
        base_action='swing' if action.startswith('swing:') else action
        q=self.current.probabilities(b,s,base_action,family,location,self.current.strength,speed=speed)
        if action.startswith('swing:'):
            outcomes=self.contacts[self.key].outcomes(b,s,hand or self.bat_hand,action.split(':')[1])
            if not outcomes:raise ValueError('해당 타격 방향의 실제 표본이 없습니다.')
            mass=sum(q[e] for e in CONTACT)
            q={e:mass*outcomes.get(e,0.) if e in CONTACT else p for e,p in q.items()}
        return q

    def deliver(self,b,s,action,pitcher,defense,rng):
        from baseball_lab.data.batting_directions import CONTACT
        probs=self.pitch_probabilities(b,s,action)
        event=rng.choices(tuple(probs),weights=tuple(probs.values()),k=1)[0]
        self.last_contact=None
        if event in CONTACT and action!='bunt':
            aim=action.split(':')[1] if action.startswith('swing:') else None
            self.last_contact=self.contacts[self.key].sample(b,s,self.bat_hand,aim,event,rng)
            self.last_contact.update(target=aim,hand=self.bat_hand)
        return event

    def run(self,o,action,rng):
        counts=self.current.running['fit'][o.outs,o.bases,o.balls,o.strikes,action]
        if sum(counts.values())<10:raise ValueError('도루의 실제 동시 투구·주자 이동 표본이 부족합니다.')
        return rng.choices(tuple(counts),weights=tuple(counts.values()),k=1)[0]

    def advance(self,outs,bases,event,rng,*,bunt=False):
        if event in ('walk','hbp'):
            end,runs=walk(bases);return outs,end,runs
        if event=='strikeout':return outs+1,bases if outs<2 else 0,0
        if event=='home_run':return outs,0,1+bases.bit_count()
        counts,_=self.current.movement(outs,bases,event,bunt)
        delta,end,runs=rng.choices(tuple(counts),weights=tuple(counts.values()),k=1)[0]
        return outs+delta,end,runs

    def state_dict(self):return {'schema':'multileague-pitch-contact-world-v3','evidence':self.evidence,'asset_sha256':ASSET_SHA256,'contact_asset_sha256':self.evidence['contact_asset_sha256']}

    def probes(self,teams):
        key=self.key;answer=[]
        for league in ('MLB','KBO','NPB'):
            available=[k for k in self.cohorts if self.cohorts[k].value['league']==league]
            if not available:continue
            tracked=[k for k in available if self.cohorts[k].patterns]
            self.key=max(tracked or available,key=lambda k:self.cohorts[k].value['season']);self.current=self.cohorts[self.key]
            self.league=league;self.season=self.current.value['season'];self.pitchers=self.current.value['pitchers']
            cues=[p for p,n in self.current.arrivals[0,0].most_common(2)]
            for family,location,speed in cues:
                for hand in sorted(self.contacts[self.key].value['hand_counts']['fit']):
                    obs=Observation(1,0,0,0,0,0,0,0,0,league,self.season,family or '',location or '',speed or '',hand)
                    legal=self.legal(obs);defense=self.defense_legal(obs);defense_obs=replace(obs,pitch_family_cue='',location_cue='',speed_cue='')
                    answer.append({'situation':'first_pitch','environment':self.key,'bat_hand':hand,'cue':pattern(family,location,speed) if family else None,'teams':[
                        {'swing':float(sum(p for a,p in zip(self.offense_actions,t[0].probabilities(obs,legal)) if a=='swing' or a.startswith('swing:'))),'offense':dict(zip(self.offense_actions,map(float,t[0].probabilities(obs,legal)))),
                         'defense':dict(zip(self.defense_actions,map(float,t[1].probabilities(defense_obs,defense))))} for t in teams]})
        self.key=key;self.current=self.cohorts[key];self.league=self.current.value['league'];self.season=self.current.value['season'];self.pitchers=self.current.value['pitchers']
        return answer

    def strategy_probes(self,teams):
        # Cover every selected year, retaining only legal nonzero probabilities.
        # No rollouts, collection or optimizer updates are performed here.
        saved=(self.key,self.current,self.league,self.season,self.pitchers,self.bat_hand);answer=[]
        try:
            for key,c in sorted(self.cohorts.items(),key=lambda item:({'MLB':0,'KBO':1,'NPB':2}[item[1].value['league']],-item[1].value['season'])):
                self.key=key;self.current=c;self.league=c.value['league'];self.season=c.value['season'];self.pitchers=c.value['pitchers']
                incoming=c.arrivals[0,0].most_common(1)
                family,location,speed=incoming[0][0] if incoming else (None,None,None)
                for hand in sorted(self.contacts[key].value['hand_counts']['fit']):
                    obs=Observation(1,0,0,0,0,0,0,0,0,self.league,self.season,family or '',location or '',speed or '',hand)
                    defense_obs=replace(obs,pitch_family_cue='',location_cue='',speed_cue='')
                    legal=self.legal(obs);defense=self.defense_legal(obs)
                    cue=pattern(family,location,speed) if family else None
                    answer.append({'id':key+'|'+hand+'|'+str(cue),
                        'context':{'environment':key,'hand':hand,'cue':cue,'balls':0,'strikes':0,'outs':0,'bases':0},
                        'teams':[{role:{a:float(p) for a,p in zip(agent.actions,agent.probabilities(observation,actions)) if p>0}
                            for role,agent,observation,actions in (('offense',team[0],obs,legal),('defense',team[1],defense_obs,defense))} for team in teams]})
        finally:self.key,self.current,self.league,self.season,self.pitchers,self.bat_hand=saved
        return answer
