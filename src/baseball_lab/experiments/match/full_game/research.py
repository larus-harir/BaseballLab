"""Observed-action whole games; final wins are the sole learning reward.

First-pitch approaches and steal donors are observational selections, not
identified causal responses to commands. No pitch physics is fabricated.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,asdict
from pathlib import Path
from random import Random
import math
import subprocess
import numpy as np
from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.r1.environment import fit,Observation as Turn,key
from baseball_lab.r1.data import walk
from baseball_lab.data.lineage import content_hash,write_json,utc_now

SCHEMA='Match-whole-game-v1'
OFF=('ordinary_turn','early_swing','take_first','bunt_attempt','steal_attempt')
DEF=('challenge','intentional_walk')
NAMES={'ordinary_turn':'일반 타격','early_swing':'초구 공략','take_first':'초구 지켜보기','bunt_attempt':'번트','steal_attempt':'도루 시도','challenge':'승부','intentional_walk':'고의볼넷'}
FEATURES=('bias','inning','bottom','outs','first','second','third','score_difference','late','leading','trailing')

@dataclass(frozen=True)
class Situation:
    inning:int
    bottom:int
    outs:int
    bases:int
    difference:int


def features(o,role):
    diff=o.difference if role=='batter' else -o.difference
    return np.array([1.,o.inning/9,o.bottom,o.outs/2,*(float(bool(o.bases&(1<<i))) for i in range(3)),math.tanh(diff/5),o.inning>=7,diff>0,diff<0],dtype=float)


def policy(role,seed):
    return NeuralPolicy(role,seed,actions=OFF if role=='batter' else DEF,feature_encoder=features,feature_names=FEATURES,observation_schema='whole-game-score-inning-v1',action_schema='observed-approaches-running-v1')


class Fixed:
    def act(self,o,legal,rng):return legal[0]


class Environment:
    def __init__(self,base,rows,steals,legal):
        self.base=base;self.legal=legal;self.cells=defaultdict(list)
        for r in rows:
            if not r['intentional_walk'] and r.get('approach') and r['action']=='ordinary_turn':self.cells[r['outs'],r['bases'],r['approach']].append(r)
        for r in steals:self.cells[r['outs'],r['bases'],'steal_attempt'].append(r)

    def game(self,learner,opponent,seed,home=True,record=False):
        rng=Random(seed);teams=(opponent,learner) if home else (learner,opponent);scores=[0,0];events=[];counts=Counter();contexts=defaultdict(Counter)
        for inning in range(1,19):
            for bottom in (0,1):
                if bottom and inning>=9 and scores[1]>scores[0]:return self.result(scores,home,events,counts,contexts,inning)
                outs=0;bases=2 if inning>9 else 0
                for turn in range(200):
                    o=Situation(inning,bottom,outs,bases,scores[bottom]-scores[1-bottom]);legal=self.legal[outs,bases]
                    b=teams[bottom][0].act(o,legal,rng);p=teams[1-bottom][1].act(o,DEF,rng)
                    if b not in legal or p not in DEF:raise ValueError('지원하지 않는 행동')
                    if (bottom==int(home)):counts[b]+=1;contexts['late' if inning>=7 else 'early'][b]+=1
                    if (1-bottom==int(home)):counts[p]+=1
                    if b=='steal_attempt':
                        donors=self.cells[outs,bases,b]
                        if not donors:raise ValueError('평가 구간에 해당 도루 상황의 실제 기록이 없습니다.')
                        r=rng.choice(donors);nxt=Turn(outs+r['outs_added'],r['end_bases']);runs=r['runs'];evidence={'donor_record_id':r['record_id'],'donor_event_codes':r['event_codes']}
                    elif b in ('early_swing','take_first') and p!='intentional_walk':
                        donors=self.cells[outs,bases,b]
                        if not donors:raise ValueError('평가 구간에 해당 타격 접근의 실제 기록이 없습니다.')
                        r=rng.choice(donors);nxt=Turn(outs+r['outs_added'],r['end_bases']);runs=r['runs'];evidence={'donor_record_id':r['record_id'],'donor_event_codes':r['event_codes']}
                    else:nxt,runs,evidence=self.base.step(Turn(outs,bases),b if b=='bunt_attempt' else 'ordinary_turn',p,rng)
                    if bottom and inning>=9 and scores[bottom]+runs>scores[1-bottom] and not any(str(c).startswith('HR') for c in evidence.get('donor_event_codes',[])):
                        runs=min(runs,scores[1-bottom]-scores[bottom]+1)
                    scores[bottom]+=runs
                    if record:events.append({'inning':inning,'bottom':bottom,'before':asdict(o),'offense':b,'defense':p,'runs':runs,'scores':scores.copy(),'after':vars(nxt),'source':{'source_status':'MODEL_SIMULATED_FROM_OBSERVED_DONOR',**evidence}})
                    outs,bases=nxt.outs,nxt.bases
                    if bottom and inning>=9 and scores[1]>scores[0]:return self.result(scores,home,events,counts,contexts,inning)
                    if outs>=3:break
                else:raise RuntimeError('한 이닝 안전 한도 초과: 승패를 만들어내지 않고 중단합니다.')
            if inning>=9 and scores[0]!=scores[1]:return self.result(scores,home,events,counts,contexts,inning)
        raise RuntimeError('18회까지 동점: 임의 승패 없이 실행을 중단합니다.')

    @staticmethod
    def result(scores,home,events,counts,contexts,inning):
        return {'reward':1 if scores[int(home)]>scores[1-int(home)] else -1,'away':scores[0],'home':scores[1],'innings':inning,'events':events,'choices':dict(counts),'contexts':{k:dict(v) for k,v in contexts.items()}}


def environments(dataset,start,end):
    bases,model=fit(dataset,start,end);parts={};banks={}
    for name,split in model['split'].items():
        parts[name]=[r for r in dataset['records'] if split['dates'][0]<=r['date']<=split['dates'][1]]
        banks[name]=[r for r in dataset.get('steal_records',[]) if split['dates'][0]<=r['date']<=split['dates'][1]]
    legal={}
    for outs in range(3):
        for bases_code in range(8):
            actions=['ordinary_turn']
            for action in OFF[1:]:
                def support(name):
                    pool=banks[name] if action=='steal_attempt' else parts[name]
                    return sum(r['outs']==outs and r['bases']==bases_code and (action=='steal_attempt' or action=='bunt_attempt' and r['action']=='bunt_attempt' or action in ('early_swing','take_first') and r.get('approach')==action and r['action']=='ordinary_turn') and not r.get('intentional_walk',False) for r in pool)
                if support('fit')>=30 and support('validation')>=10:actions.append(action)
            legal[outs,bases_code]=tuple(actions)
    return {n:Environment(bases[n],parts[n],banks[n],legal) for n in parts},model,legal


def evaluate(env,pair,n,seed,opponent=None):
    opponent=opponent or (Fixed(),Fixed());games=[env.game(pair,opponent,seed+i*7919,home=bool(i%2)) for i in range(n)]
    wins=sum(g['reward']==1 for g in games);p=wins/n;z=1.96;d=1+z*z/n
    mid=(p+z*z/(2*n))/d;radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return {'games':n,'wins':wins,'win_rate':p,'wilson_95':[mid-radius,mid+radius],'scope':'simulation sampling uncertainty only; not real baseball predictive accuracy'}


def train(dataset,start,end,output,config):
    config.validate();output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('기존 결과를 덮어쓸 수 없습니다.')
    if dataset['manifest']['source_status']!='REAL_OBSERVED':raise ValueError('실제 기록만 사용합니다.')
    envs,model,legal=environments(dataset,start,end);output.mkdir(parents=True,exist_ok=True)
    result={'schema':SCHEMA,'status':'RUNNING','created_at':utc_now(),'dataset':dataset['manifest'],'split':model['split'],'config':asdict(config),
        'reward':'final team win +1, loss -1; no intermediate run/action reward','rules':'9 innings, skip bottom ninth if home ahead, walkoff, extras start runner on second; 18-inning safety abort',
        'action_names':NAMES,'supported_actions':sorted({a for v in legal.values() for a in v}|set(DEF)),
        'limitations':['Observed-action resampling is not an identified causal effect of commanding that action.','No pitch type/location/velocity, lineup optimization, individual player ability, pitcher substitutions, defensive shifts or fatigue is learned in this version.','Regular innings 1–8 donors are transported into late innings and extras; this assumption is unvalidated.','Extra-inning runner uses an explicit modern MLB rule even when older source seasons are selected.'],
        'seeds':[],'code_scope':'Whole-game extension of the shared observed-turn engine; preserves inning studies.'}
    source_root=Path(__file__).resolve().parents[3]
    result['source_hash']=content_hash({str(p.relative_to(source_root)):p.read_text(encoding='utf-8') for p in sorted(source_root.rglob('*.py'))})
    try:result['code_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):result['code_commit']='unknown'
    result['action_availability']={f'{o}:{b}':list(actions) for (o,b),actions in legal.items()}
    result['run_id']=content_hash({'schema':SCHEMA,'data':dataset['manifest']['dataset_id'],'config':asdict(config),'code':result['source_hash']})
    for seed in config.seeds:
        rng=Random(seed);pair=(policy('batter',seed),policy('pitcher',seed+1));initial=tuple(a.frozen() for a in pair);archives=[initial];batch=[[],[]];choices=Counter();contexts=defaultdict(Counter)
        run={'seed':seed,'history':[]};result['seeds'].append(run)
        def checkpoint(done):
            frozen=tuple(a.frozen() for a in pair)
            for a in pair:a.collect=False
            probes=[]
            for inning in (1,9):
                for difference in (-2,0,2):
                    o=Situation(inning,1,1,1,difference)
                    for role,a,actions in (('공격',frozen[0],legal[1,1]),('수비',frozen[1],DEF)):
                        probes.append({'inning':inning,'difference':difference,'role':role,'probabilities':dict(zip(a.actions,map(float,a.probabilities(o,actions))))})
            run['history'].append({'probes':probes,'games':done,'validation':evaluate(envs['validation'],frozen,config.evaluation_n,seed+100000),'choices':dict(choices),'contexts':{k:dict(v) for k,v in contexts.items()}})
            write_json(output/'checkpoints'/f'{seed}-{done}.json',{'schema':SCHEMA,'batter':pair[0].state_dict(),'pitcher':pair[1].state_dict(),'data_id':dataset['manifest']['dataset_id']})
            archives.append(frozen);write_json(output/'research.json',result);report(output,result)
        checkpoint(0)
        for episode in range(1,config.episodes+1):
            opponent=(Fixed(),Fixed()) if episode%3==0 else rng.choice(archives)
            for a in pair:a.collect=True;a.decisions=[]
            game=envs['fit'].game(pair,opponent,rng.randrange(2**31),home=bool(episode%2))
            for i,a in enumerate(pair):batch[i].append((list(a.decisions),game['reward']))
            choices.update(game['choices'])
            for k,v in game['contexts'].items():contexts[k].update(v)
            if episode%config.batch_size==0 or episode%config.evaluate_every==0 or episode==config.episodes:
                for i,a in enumerate(pair):a.update(batch[i]);batch[i]=[]
            if episode%config.evaluate_every==0 or episode==config.episodes:
                print(f'학습 {episode}/{config.episodes}경기',flush=True);checkpoint(episode)
        run['test_before']=evaluate(envs['test'],initial,config.evaluation_n,seed+200000)
        run['test_after']=evaluate(envs['test'],tuple(a.frozen() for a in pair),config.evaluation_n,seed+200000)
        run['replay']=envs['test'].game(tuple(a.frozen() for a in pair),(Fixed(),Fixed()),seed+300000,home=True,record=True)
        run['optimizer_steps']=[a.steps for a in pair]
        run['parameters_changed']=[any(not np.array_equal(x,y) for x,y in zip(before.params,after.params)) for before,after in zip(initial,pair)]
    result['status']='COMPLETED';write_json(output/'research.json',result);report(output,result)
    return result


def render(result):
    from .results import render as render_teams
    return render_teams(result)


def report(output,result):
    Path(output/'report.html').write_text(render(result),encoding='utf-8')
