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
    import html,json
    data=json.dumps(result,ensure_ascii=False).replace('<','\\u003c')
    return '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>전체 경기 전략 학습 결과</title><style>body{font:16px/1.7 system-ui;background:#f5f3ed;color:#152c38;max-width:1100px;margin:auto;padding:25px}section{background:white;padding:22px;border-radius:16px;margin:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}button{padding:10px}a{color:#147168}</style><a href="/match">AI 전략 연구</a><h1>전체 경기 전략 학습</h1><p>공격과 수비를 모두 맡는 AI가 경기 마지막의 승패로 학습합니다.</p><section><h2>학습 전후 승률</h2><div id="scores"></div><p>같은 고정 상대에게 홈·원정을 번갈아 평가했습니다. 실제 리그 승률이 아니라, 이 시뮬레이션에서의 성적입니다. 작은 차이와 겹치는 구간만으로 성장을 단정하지 않습니다.</p></section><section><h2>어떤 플레이를 선택했나요?</h2><h3>같은 상황에서 달라진 선택 확률</h3><div id="policyChanges"></div><h3>실제로 선택한 횟수</h3><div id="choices"></div><p>전략 이름이나 번트·도루 권장 비율을 학습 정답으로 주지 않습니다. 최종 승리만 보상으로 사용합니다.</p></section><section><h2>학습 과정</h2><div id="curve"></div></section><section><h2>경기 흐름 보기</h2><label>장면 <input id="pos" type="range" min="0" value="0"></label><div id="scene"></div></section><section><h2>무엇을 할 수 있나요?</h2><p id="actions"></p><p>아직 타순·투수 교체·구종·코스·수비 배치를 배우는 기능은 없습니다. 초구 접근과 도루 등은 실제 관측 장면을 재표집한 것이며 명령의 인과 효과는 검증 전입니다.</p><details><summary>자료·평가 기간·모형의 가정</summary><pre id="details" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details></section><script>const r=DATA,$=id=>document.getElementById(id),pct=x=>(100*x).toFixed(1)+'%',table=(heads,rows)=>'<div class="scroll"><table><tr>'+heads.map(x=>'<th>'+x+'</th>').join('')+'</tr>'+rows.map(row=>'<tr>'+row.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</table></div>';const name=x=>r.action_names[x]||x;
$('scores').innerHTML=table(['반복','학습 전','학습 후','학습 후 95% 구간'],r.seeds.map(s=>[s.seed,s.test_before?pct(s.test_before.win_rate):'학습 중',s.test_after?pct(s.test_after.win_rate):'평가 전',s.test_after?s.test_after.wilson_95.map(pct).join(' ~ '):'평가 전']));
const changes=r.seeds.flatMap(s=>(s.history[0]?.probes||[]).flatMap((a,i)=>Object.entries(a.probabilities).map(([k,v])=>({seed:s.seed,role:a.role,inning:a.inning,diff:a.difference,action:k,before:v,after:s.history.at(-1).probes[i].probabilities[k]})))).sort((a,b)=>Math.abs(b.after-b.before)-Math.abs(a.after-a.before)).slice(0,6);$('policyChanges').innerHTML=table(['반복','상황 (1아웃 1루)','행동','학습 전','학습 후'],changes.map(c=>[c.seed,c.role+' · '+c.inning+'회 · '+(c.diff>0?c.diff+'점 앞섬':c.diff<0?-c.diff+'점 뒤짐':'동점'),name(c.action),pct(c.before),pct(c.after)]));
$('choices').innerHTML=table(['반복','행동','실제 선택 수'],r.seeds.flatMap(s=>Object.entries(s.history.at(-1)?.choices||{}).map(([k,v])=>[s.seed,name(k),v])));$('curve').innerHTML=table(['반복','학습한 경기','중간 점검 승률'],r.seeds.flatMap(s=>s.history.map(h=>[s.seed,h.games,pct(h.validation.win_rate)])));
$('actions').textContent=r.supported_actions.map(name).join(' · ');$('details').textContent=JSON.stringify({reward:r.reward,rules:r.rules,split:r.split,source:r.dataset,limitations:r.limitations},null,2);const events=r.seeds[0]?.replay?.events||[];$('pos').max=Math.max(0,events.length-1);function scene(){const e=events[Number($('pos').value)];$('scene').textContent=e?e.inning+'회 '+(e.bottom?'말':'초')+' · '+e.before.outs+'아웃 · 주자 코드 '+e.before.bases+' · '+name(e.offense)+' / '+name(e.defense)+' → '+e.runs+'득점 · 원정 '+e.scores[0]+' : 홈 '+e.scores[1]:'학습 종료 후 실제 실행 장면을 표시합니다.'}$('pos').oninput=scene;scene();</script>'''.replace('DATA',data)


def report(output,result):
    Path(output/'report.html').write_text(render(result),encoding='utf-8')
