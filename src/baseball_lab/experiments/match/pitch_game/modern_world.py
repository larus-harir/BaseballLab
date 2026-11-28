"""Shared modern-baseball learner: partial observations remain useful evidence."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import gzip,hashlib,json
import numpy as np
from dataclasses import replace
from baseball_lab.agents.neural import NeuralPolicy
from .corpus_world import CorpusWorld,FAMILY_CUES,legal_movement
from .tracking_world import TrackingWorld,features as tracking_features,LOCATIONS
from .research import FEATURES

ASSET='unified-modern-baseball-v1.json.gz'
ASSET_SHA256='b7361614f053257c6f5581ad3aeced181b1ca4d33c7ba2a2194018c69b7a19af'
HISTORY_FIELDS=('H','HR','SO','BB','R_per_team_game')


@lru_cache(maxsize=1)
def data():
    body=files('baseball_lab').joinpath('data/resources',ASSET).read_bytes()
    if hashlib.sha256(body).hexdigest()!=ASSET_SHA256:raise ValueError('통합 야구 기록의 지문 불일치')
    value=json.loads(gzip.decompress(body))
    if value['schema']!='unified-modern-baseball-v1' or value['source_status']!='REAL_OBSERVED':raise ValueError('실제 통합 기록만 사용합니다.')
    value['_asset_sha256']=ASSET_SHA256
    for s in value['sources']:
        s.setdefault('credit',s.get('repository','Source counts'));s.setdefault('signature',s.get('manifest_sha256',s.get('source_signature')))
    return value


def inventory():
    d=data();cohorts=d['cohorts'];by_league=Counter(c['league'] for c in cohorts.values())
    history={l:sorted(int(k.split(':')[1]) for k in d['annual_history'] if k.startswith(l+':')) for l in by_league}
    return {'schema':'pitch-training-inventory-v3','start_year':2010,'cycle_games':len(by_league)*max(by_league.values()),'history':history,'cohorts':[
      {'id':k,'league':c['league'],'season':c['season'],'rows':c['source_rows'],'fit_pitches':c['used_pitches']['fit'],
       'native_movements':c['used_movements']['fit'],'capabilities':c['capabilities']['fit'],
       'location':('구종·코스·구속과 타격·주루' if c['capabilities']['fit']['course'] else '구종·구속과 타격·주루' if c['capabilities']['fit']['family'] else '카운트·타격·주루')}
       for k,c in cohorts.items()], 'bytes':files('baseball_lab').joinpath('data/resources',ASSET).stat().st_size}


@lru_cache(maxsize=128)
def historical_context(league,season):
    totals={k:Counter() for k in HISTORY_FIELDS};used=[]
    for key,fields in data()['annual_history'].items():
        l,y=key.split(':')
        if l!=league or not 2010<=int(y)<season:continue
        used.append(int(y))
        for k,v in fields.items():totals[k].update(v)
    values=[]
    for k in HISTORY_FIELDS:
        n=totals[k];values.extend((n['n']/n['d']/(10 if k=='R_per_team_game' else 1) if n['d'] else 0.,float(bool(n['d']))))
    return tuple(values),tuple(sorted(used))


def features(o,role):
    history,_=historical_context(o.league,o.season)
    return np.concatenate((tracking_features(o,role),[bool(o.pitch_family_cue),bool(o.location_cue),bool(o.speed_cue)],history))


class ModernWorld(TrackingWorld):
    result_schema='Match-pitch-decision-game-v8'
    def __init__(self,leagues=None,seasons=None,*,learner='ppo',cached_validation=True):
        from .validated_world import load
        validation=load(ASSET_SHA256) if cached_validation else None
        self.learner=learner
        if learner not in ('ppo','reinforce'):raise ValueError('Unsupported learner')
        self.result_schema='Match-pitch-decision-game-v8' if learner=='ppo' else 'Match-pitch-decision-game-v6'
        raw=data();contact={'base_asset_sha256':ASSET_SHA256,'_asset_sha256':ASSET_SHA256,'cohorts':raw['contacts'],
            'assumptions':['Contact targets use observed directional samples, not recorded intention. Non-contact probabilities remain shared with ordinary swings. KBO directional supplementary samples retain their own population.']}
        CorpusWorld.__init__(self,leagues,seasons,dataset=raw,contact_data=contact,validation_data=validation)
        self.defense_actions=tuple(sorted(self.defense_actions))
        self._offense_cache={};self._defense_cache={};self._movement_backoffs={}
        self._eligible={}
        for key,c in self.cohorts.items():
            counts=Counter()
            for cell,values in c.counts['fit'].items():counts[cell[3:]]+=sum(values.values())
            self._eligible[key]=counts
        self.evidence.update(model='unified-modern-baseball-v1',shared_learning=True,
            quality=raw['quality'],start_year=2010,validation_reused=bool(validation),
            learning_algorithm='Clipped on-policy terminal-win PPO with learned win-value baseline' if learner=='ppo' else 'Legacy terminal-return REINFORCE',
            capabilities={k:c.value['capabilities'] for k,c in self.cohorts.items()},
            movement_sources={k:c.value.get('movement_source',c.value['source']) for k,c in self.cohorts.items()},
            historical_context={k:{'seasons':historical_context(c.value['league'],c.value['season'])[1],
                'values':historical_context(c.value['league'],c.value['season'])[0]} for k,c in self.cohorts.items()},
            annual_coverage=inventory()['history'],
            training_goal='One shared offense and pitching policy learn from both roles across all available modern league/year environments.',
            missing_policy='Unknown features are masked; partial records teach supported decisions and native outcomes. No invented course and no source-level season exclusion for tracking absence.',
            batting_model='One offense policy shares both trajectory roles. Reported stance is not inferred from pitcher handedness.',
            coordinate_contract='Source-normalized left/center/right; derived KBO height and SPAIA display positions remain separately documented.',
            evaluation_sampling='Equal league opportunities, within-league year cycles and identical-state preference probes; no team ranking tournament.')
        if learner=='ppo':
            self.evidence['policy_head']='Joint pitch logits plus shared family/course/speed residual factors; no fixed preference or auxiliary baseball reward.'
            self.evidence['pitch_credit']='terminal-win-ppo-shared-pitch-gae-v2'
            self.evidence['feedback_contract']='Executed outcomes and pre-update terminal-win advantages. Contact-kind associations are not identified causal effects of pitch choice.'
            self.evidence['transition_backoff']+=' If native support is empty, use exact base/out/event/bunt observations from completed earlier seasons of the same league, fit splits only. Never use a future season, other league or invented transition.'
            self.evidence['supplemental_movement_backoffs']=[]

    def new_team(self,seed):
        names=(*FEATURES,'MLB','KBO','NPB','season',*('cue_'+f for f in FAMILY_CUES),*('cue_'+v for v in LOCATIONS),
           'cue_slow','cue_middle_speed','cue_fast','bat_left','bat_right','has_family_cue','has_course_cue','has_speed_cue',
           *(n for f in HISTORY_FIELDS for n in ('history_'+f,'has_history_'+f)))
        from baseball_lab.agents.win_policy import WinPolicy,PitchCreditPolicy
        agents=tuple((WinPolicy if role=='batter' else PitchCreditPolicy)(role,seed+i,actions=self.offense_actions if role=='batter' else self.defense_actions,
            feature_encoder=features,feature_names=names,observation_schema='unified-modern-observation-v1',action_schema='unified-modern-actions-v3') if self.learner=='ppo' else NeuralPolicy(role,seed+i,actions=self.offense_actions if role=='batter' else self.defense_actions,
            feature_encoder=features,feature_names=names,observation_schema='unified-modern-observation-v1',action_schema='unified-modern-actions-v1') for i,role in enumerate(('batter','pitcher')))
        for agent in agents:agent.params[-2].fill(0.)
        return agents

    def defense_legal(self,o):
        key=(self.key,o.pitcher)
        if key in self._defense_cache:return list(self._defense_cache[key])
        actions=['pitch','intentional_walk'];c=self.current;pid=self.pitchers[o.pitcher]
        families=c.value['pitcher_repertoires'].get(pid,{});speeds=c.value.get('pitcher_speed_repertoires',{}).get(pid,{})
        for name,(family,location,speed) in c.patterns.items():
            if self._eligible[self.key][family,location,speed]<20 or families.get(family,0)<10:continue
            if speed and speeds.get(family+'|'+speed,0)<10:continue
            actions.append(name)
        if self.learner=='ppo':
            candidates=[(name,c.patterns[name]) for name in actions if name in c.patterns]
            speed_known={f for name,(f,l,s) in candidates if s is not None}
            candidates=[(name,p) for name,p in candidates if p[2] is not None or p[0] not in speed_known]
            course_known={(f,s) for name,(f,l,s) in candidates if l is not None}
            candidates=[(name,p) for name,p in candidates if p[1] is not None or (p[0],p[2]) not in course_known]
            # Missing measurements are not intentional targets; their observed
            # outcomes still fit the same count/action prior and native world.
            actions=['intentional_walk',*(name for name,p in candidates)] if candidates else ['pitch','intentional_walk']
        self._defense_cache[key]=tuple(sorted(actions))
        return list(self._defense_cache[key])

    def prepare(self,o,defense,rng):return CorpusWorld.prepare(self,o,defense,rng)

    def advance(self,outs,bases,event,rng,*,bunt=False):
        try:return CorpusWorld.advance(self,outs,bases,event,rng,bunt=bunt)
        except ValueError:
            if self.learner!='ppo':raise
            key=(self.key,outs,bases,event,bunt)
            if key not in self._movement_backoffs:
                counts=Counter();sources=[]
                for name,c in data()['cohorts'].items():
                    if c['league']!=self.league or c['season']>=self.season:continue
                    if c['split']['fit'][1]>=self.current.value['split']['fit'][0]:continue
                    observed=Counter()
                    for o,b,e,is_bunt,values in c['movements']['fit']:
                        if (o,b,e,is_bunt)!=(outs,bases,event,bunt):continue
                        for delta,end,runs,n in values:
                            if legal_movement(outs,bases,event,delta,end,runs):observed[delta,end,runs]+=n
                    if observed:counts.update(observed);sources.append({'environment':name,'fit_end':c['split']['fit'][1],'observations':sum(observed.values())})
                if not counts:raise ValueError(f'{self.league} {self.season}의 해당 진루와 동일한 과거 관측도 없습니다.')
                self._movement_backoffs[key]=counts
                self.evidence['supplemental_movement_backoffs'].append({'environment':self.key,'outs':outs,'bases':bases,'event':event,'bunt':bunt,
                    'basis':'same league, earlier completed season, fit-only exact state/event','sources':sources,'outcomes':[[*target,n] for target,n in sorted(counts.items())]})
            counts=self._movement_backoffs[key]
        delta,end,runs=rng.choices(tuple(counts),weights=tuple(counts.values()),k=1)[0]
        return outs+delta,end,runs

    def legal(self,o):
        key=(self.key,o.balls,o.strikes,o.bat_hand,o.outs,o.bases)
        if key in self._offense_cache:return self._offense_cache[key]
        actions=list(CorpusWorld.legal(self,o));c=self.current
        # Explicit observed bunt misses/fouls distinguish real attempt data
        # from providers that only label successful contact as a bunt.
        misses=sum(n.get('strike',0)+n.get('bunt_foul',0) for (b,s,a),n in c.base['fit'].items() if a=='bunt')
        if 'bunt' not in actions and misses>=10 and sum(c.base['fit'].get((o.balls,o.strikes,'bunt'),{}).values())>=10:
            try:
                for event in ('out','single'):c.movement(o.outs,o.bases,event,True)
                actions.append('bunt')
            except ValueError:pass
        self._offense_cache[key]=tuple(actions)
        return self._offense_cache[key]

    def strategy_probes(self,teams):
        answer=CorpusWorld.strategy_probes(self,teams)
        if self.learner!='ppo':return answer
        from .research import Observation
        saved=(self.key,self.current,self.league,self.season,self.pitchers,self.bat_hand)
        scenarios=tuple((f'count_{b}_{s}',4,0,1,0,0,b,s) for b in range(4) for s in range(3))+(('two_strikes',6,1,1,2,-1,0,2),('hitter_count',4,0,0,0,0,3,1),
                   ('double_play',7,0,0,1,0,1,1),('late_lead',9,0,2,0,-1,1,2))
        try:
            for league in sorted({c.value['league'] for c in self.cohorts.values()}):
                key=max((k for k,c in self.cohorts.items() if c.value['league']==league),key=lambda k:self.cohorts[k].value['season'])
                c=self.cohorts[key];self.key=key;self.current=c;self.league=league;self.season=c.value['season'];self.pitchers=c.value['pitchers']
                for name,inning,bottom,outs,bases,difference,balls,strikes in scenarios:
                    incoming=c.arrivals[balls,strikes] or c.arrivals[0,0]
                    family,area,speed=incoming.most_common(1)[0][0]
                    for hand in sorted(self.contacts[key].value['hand_counts']['fit']):
                        o=Observation(inning,bottom,outs,bases,difference,balls,strikes,0,3,league,self.season,family or '',area or '',speed or '',hand)
                        defense=replace(o,pitch_family_cue='',location_cue='',speed_cue='');legal=(self.legal(o),self.defense_legal(o))
                        cue='pitch:'+str(family)+':'+(area or 'any')+':'+(speed or 'missing') if family else None
                        answer.append({'id':key+'|'+hand+'|'+name,'context':{'environment':key,'name':name,'inning':inning,'bottom':bottom,
                            'difference':difference,'balls':balls,'strikes':strikes,'outs':outs,'bases':bases,'hand':hand,'cue':cue},
                            'teams':[{role:{a:float(p) for a,p in zip(agent.actions,agent.probabilities(obs,options)) if p>0}
                             for role,agent,obs,options in (('offense',team[0],o,legal[0]),('defense',team[1],defense,legal[1]))} for team in teams]})
        finally:self.key,self.current,self.league,self.season,self.pitchers,self.bat_hand=saved
        return answer

    def state_dict(self):return {'schema':'unified-modern-baseball-v1','evidence':self.evidence,'asset_sha256':ASSET_SHA256}
