"""Shared modern-baseball learner: partial observations remain useful evidence."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import gzip,hashlib,json
import numpy as np
from baseball_lab.agents.neural import NeuralPolicy
from .corpus_world import CorpusWorld,FAMILY_CUES
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
    result_schema='Match-pitch-decision-game-v6'
    def __init__(self,leagues=None,seasons=None):
        raw=data();contact={'base_asset_sha256':ASSET_SHA256,'_asset_sha256':ASSET_SHA256,'cohorts':raw['contacts'],
            'assumptions':['Contact targets use observed directional samples, not recorded intention. Non-contact probabilities remain shared with ordinary swings. KBO directional supplementary samples retain their own population.']}
        CorpusWorld.__init__(self,leagues,seasons,dataset=raw,contact_data=contact)
        self._eligible={}
        for key,c in self.cohorts.items():
            counts=Counter()
            for cell,values in c.counts['fit'].items():counts[cell[3:]]+=sum(values.values())
            self._eligible[key]=counts
        self.evidence.update(model='unified-modern-baseball-v1',shared_learning=True,
            quality=raw['quality'],start_year=2010,
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

    def new_team(self,seed):
        names=(*FEATURES,'MLB','KBO','NPB','season',*('cue_'+f for f in FAMILY_CUES),*('cue_'+v for v in LOCATIONS),
           'cue_slow','cue_middle_speed','cue_fast','bat_left','bat_right','has_family_cue','has_course_cue','has_speed_cue',
           *(n for f in HISTORY_FIELDS for n in ('history_'+f,'has_history_'+f)))
        agents=tuple(NeuralPolicy(role,seed+i,actions=self.offense_actions if role=='batter' else self.defense_actions,
            feature_encoder=features,feature_names=names,observation_schema='unified-modern-observation-v1',action_schema='unified-modern-actions-v1') for i,role in enumerate(('batter','pitcher')))
        for agent in agents:agent.params[-2].fill(0.)
        return agents

    def defense_legal(self,o):
        actions=['pitch','intentional_walk'];c=self.current;pid=self.pitchers[o.pitcher]
        families=c.value['pitcher_repertoires'].get(pid,{});speeds=c.value.get('pitcher_speed_repertoires',{}).get(pid,{})
        for name,(family,location,speed) in c.patterns.items():
            if self._eligible[self.key][family,location,speed]<20 or families.get(family,0)<10:continue
            if speed and speeds.get(family+'|'+speed,0)<10:continue
            actions.append(name)
        return actions

    def prepare(self,o,defense,rng):return CorpusWorld.prepare(self,o,defense,rng)

    def legal(self,o):
        actions=list(CorpusWorld.legal(self,o));c=self.current
        # Explicit observed bunt misses/fouls distinguish real attempt data
        # from providers that only label successful contact as a bunt.
        misses=sum(n.get('strike',0)+n.get('bunt_foul',0) for (b,s,a),n in c.base['fit'].items() if a=='bunt')
        if 'bunt' not in actions and misses>=10 and sum(c.base['fit'].get((o.balls,o.strikes,'bunt'),{}).values())>=10:
            try:
                for event in ('out','single'):c.movement(o.outs,o.bases,event,True)
                actions.append('bunt')
            except ValueError:pass
        return tuple(actions)

    def state_dict(self):return {'schema':'unified-modern-baseball-v1','evidence':self.evidence,'asset_sha256':ASSET_SHA256}
