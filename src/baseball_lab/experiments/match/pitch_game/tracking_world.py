"""One shared policy pair learns from three native, observed-course domains."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
from random import Random
import gzip,hashlib,json
import numpy as np
from baseball_lab.agents.neural import NeuralPolicy
from .corpus_world import CorpusWorld,FAMILY_CUES
from .research import FEATURES,features as original_features

ASSET='observed-tracking-worlds-v1.json.gz'
ASSET_SHA256='6f292a4114abe5d8ce8db5ad86aac1fbde260b742a3ffdcd012da3fd203457fb'
LOCATIONS=tuple(h+'_'+v for h in ('left','middle','right') for v in ('low','middle','high'))


@lru_cache(maxsize=1)
def data():
    body=files('baseball_lab').joinpath('data','resources',ASSET).read_bytes()
    if hashlib.sha256(body).hexdigest()!=ASSET_SHA256:raise ValueError('추적 교재 지문 불일치')
    d=json.loads(gzip.decompress(body))
    if d['schema']!='observed-tracking-worlds-v1' or d['source_status']!='REAL_OBSERVED':raise ValueError('실제 추적 자료만 사용합니다.')
    d['_asset_sha256']=ASSET_SHA256
    for source in d['sources']:
        source.setdefault('credit',source['repository']);source.setdefault('signature',source.get('manifest_sha256',source.get('source_signature')))
        if source['league']=='NPB':source['credit']='This uses data sourced from the Nippon Baseball Data Repository, which can be accessed here: https://github.com/armstjc/Nippon-Baseball-Data-Repository'
    return d


def inventory():
    d=data();cohorts=d['cohorts'];maximum=max(Counter(c['league'] for c in cohorts.values()).values())
    return {'schema':'pitch-training-inventory-v2','cycle_games':3*maximum,'cohorts':[
        {'id':k,'league':v['league'],'season':v['season'],'rows':v['source_rows'],'fit_pitches':v['used_pitches']['fit'],
         'native_movements':v['used_movements']['fit'],'location':'실제 추적 구종·구속·코스 · KBO는 롯데 참가 경기' if v['league']=='KBO' else '실제 추적 구종·구속·코스'} for k,v in cohorts.items()],
        'bytes':files('baseball_lab').joinpath('data','resources',ASSET).stat().st_size}


def features(o,role):
    return np.concatenate((original_features(o,role),[float(o.league==l) for l in ('MLB','KBO','NPB')],[(o.season-2000)/50],
        [float(o.pitch_family_cue==f) for f in FAMILY_CUES],[float(o.location_cue==c) for c in LOCATIONS],
        [float(o.speed_cue==v) for v in ('slow','middle','fast')],[float(o.bat_hand==h) for h in ('L','R')]))


class TrackingWorld(CorpusWorld):
    shared_learning=True
    def __init__(self,leagues=None,seasons=None):
        raw=data();contact={'base_asset_sha256':ASSET_SHA256,'_asset_sha256':ASSET_SHA256,'cohorts':raw['contacts'],
            'assumptions':['Directional intent is an idealized contact target, not observed human intention; non-contact rates remain shared with ordinary swings.']}
        super().__init__(leagues,seasons,dataset=raw,contact_data=contact)
        self.defense_actions=tuple(k for k in self.defense_actions if k!='pitch')
        self.evidence.update(model='shared-observed-course-world-v1',shared_learning=True,quality=raw['quality'],
           batting_model='One shared offense policy across both trajectory roles. Virtual stance is sampled from fit-only reported stance frequencies; no individual batter ability is assigned.',
           training_goal='One offense policy and one pitching policy share both sides of self-play across MLB/KBO/NPB. Teams are trajectory roles, not research competitors.',
           sampling='Equal league opportunity; years cycle without replacement inside each league. Raw source volumes and game opportunities are reported separately.',
           coordinate_contract='Left/center/right and height are normalized in each documented source display frame; not a claim of identical physical tracking systems.',
           evaluation_sampling='Identical-state policy probes and pooled executed choices, without ranking tournaments. Equal league opportunities; years cycle within each league.')
        self._eligible={}
        for key,c in self.cohorts.items():
            total=Counter()
            for cell,counts in c.counts['fit'].items():total[cell[3:]]+=sum(counts.values())
            self._eligible[key]=total

    def new_team(self,seed):
        names=(*FEATURES,'MLB','KBO','NPB','season',*('cue_'+f for f in FAMILY_CUES),*('cue_'+v for v in LOCATIONS),'cue_slow','cue_middle_speed','cue_fast','bat_left','bat_right')
        team=tuple(NeuralPolicy(role,seed+i,actions=self.offense_actions if role=='batter' else self.defense_actions,
            feature_encoder=features,feature_names=names,observation_schema='tracking-shared-observation-v1',action_schema='tracking-shared-actions-v1') for i,role in enumerate(('batter','pitcher')))
        for a in team:a.params[-2].fill(0.)
        return team

    def defense_legal(self,o):
        repertoire=self.current.value['pitcher_speed_repertoires'].get(self.pitchers[o.pitcher],{})
        actions=['intentional_walk']
        for name,(family,location,speed) in self.current.patterns.items():
            if self._eligible[self.key][family,location,speed]>=20 and repertoire.get(family+'|'+str(speed),0)>=10:actions.append(name)
        if len(actions)==1:raise ValueError('해당 투수의 코스 추적 표본이 충분하지 않습니다.')
        return actions

    def training_context(self,seed,episode):
        leagues=sorted({c.value['league'] for c in self.cohorts.values()});cycle=(episode-1)//len(leagues);order=list(leagues)
        Random(seed+(cycle//max(1,len(self.cohorts)))*100003).shuffle(order);league=order[(episode-1)%len(order)]
        keys=sorted(k for k,c in self.cohorts.items() if c.value['league']==league)
        rng=Random(seed+leagues.index(league)*1009+(cycle//len(keys))*100003);rng.shuffle(keys)
        return keys[cycle%len(keys)]

    def prepare(self,o,defense,rng):
        if defense not in self.current.patterns:raise ValueError('추적 코스가 있는 투구 패턴을 선택해야 합니다.')
        return super().prepare(o,defense,rng)

    def state_dict(self):return {'schema':'shared-observed-course-world-v1','evidence':self.evidence,'asset_sha256':ASSET_SHA256}
