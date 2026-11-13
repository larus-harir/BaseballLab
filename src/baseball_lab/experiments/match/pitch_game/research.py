"""Fit a numerical pitch world, then let two teams learn final wins inside it.
No historical outcome row is sampled during a simulated game. No pitch type,
location or velocity is invented. Observed-action associations remain an
unidentified counterfactual assumption and are reported as such.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,asdict
from pathlib import Path
from random import Random
import math
import numpy as np
from baseball_lab.agents.neural import NeuralPolicy
from baseball_lab.core.engine import State,transition
from baseball_lab.core.contracts import RuleSet
from baseball_lab.r1.data import walk
from baseball_lab.data.lineage import content_hash,write_json,utc_now

SCHEMA='Match-pitch-decision-game-v1'
EVENTS=('ball','strike','foul','out','single','double','triple','home_run','hbp')
OFF=('take','swing');DEF=('pitch','intentional_walk','change_1','change_2')
NAMES={'take':'지켜보기','swing':'스윙','pitch':'현재 투수로 투구','intentional_walk':'고의볼넷','change_1':'두 번째 투수로 교체','change_2':'세 번째 투수로 교체'}


def sequence(turn):
    if turn['intentional_walk']:return []
    codes=[c for c in turn['pitches'] if c.isalpha()]
    if not codes or any(c not in 'BCSFTXH' for c in codes):return []
    balls=strikes=0;rows=[];terminal=False
    for i,c in enumerate(codes):
        if terminal:return []
        action='take' if c in 'BCH' else 'swing'
        event='ball' if c=='B' else 'strike' if c in 'CST' else 'foul' if c=='F' else 'hbp' if c=='H' else turn['event']
        if event in ('walk','strikeout'):return []
        rows.append((balls,strikes,action,event))
        if event=='ball':balls+=1;terminal=balls==4
        elif event=='strike':strikes+=1;terminal=strikes==3
        elif event=='foul':strikes=min(2,strikes+1)
        else:terminal=True
    end='walk' if balls==4 else 'strikeout' if strikes==3 else rows[-1][3]
    if not terminal or end!=turn['event']:return []
    return rows


def allowed(action):return ('ball','strike','hbp') if action=='take' else ('strike','foul','out','single','double','triple','home_run')


class World:
    def __init__(self,data):
        turns=data['pitch_turns'];days=sorted({r['date'] for r in turns})
        if len(days)<3:raise ValueError('투구 기록의 학습·점검·평가 날짜가 부족합니다.')
        a=max(1,int(len(days)*.6));b=min(len(days)-1,max(2,int(len(days)*.8)))
        bounds=(days[a],days[b]);parts={k:[r for r in turns if low<=r['date']<=high] for k,low,high in [('fit',days[0],days[a-1]),('validation',days[a],days[b-1]),('test',days[b],days[-1])]}
        parsed={k:[(r,seq) for r in rows if (seq:=sequence(r))] for k,rows in parts.items()}
        self.pitchers=[p for p,_ in Counter(r['pitcher'] for r,seq in parsed['fit']).most_common(3)]
        if len(self.pitchers)<3:raise ValueError('서로 다른 투수 세 명의 학습 구간 기록이 필요합니다.')
        self.split={k:{'dates':[min(r['date'] for r in rows),max(r['date'] for r in rows)],'turns':len(rows)} for k,rows in parts.items()}
        def samples(key):return [(r,b,s,act,event) for r,seq in parsed[key] for b,s,act,event in seq]
        fit=samples('fit');val=samples('validation');test=samples('test')
        if len(fit)<1000 or min(len(val),len(test))<100:raise ValueError('선정 투수들의 투구 표본이 부족합니다.')
        self.supported={a:{e for r,b,s,action,e in fit if action==a} for a in OFF}
        if not all(self.supported.values()):raise ValueError('스윙·지켜보기의 실제 투구 표본이 모두 필요합니다.')
        x=np.array([self.vector(b,s,a,r['pitcher']) for r,b,s,a,e in fit]);y=np.array([EVENTS.index(e) for r,b,s,a,e in fit]);masks=np.array([self.mask(a) for r,b,s,a,e in fit])
        self.w=np.zeros((x.shape[1],len(EVENTS)));rng=np.random.default_rng(83)
        for _ in range(500):
            ix=rng.integers(0,len(x),min(1024,len(x)));q=self.batch(x[ix],masks[ix]);q[np.arange(len(ix)),y[ix]]-=1
            self.w-=.08*(x[ix].T@q/len(ix)+.0001*self.w)
        self.runner=defaultdict(Counter)
        for r,seq in parsed['fit']:
            self.runner[r['outs'],r['bases'],r['event']][r['outs_added'],r['end_bases'],r['runs']]+=1
        baseline=defaultdict(Counter);pooled=defaultdict(Counter)
        for r,b,s,a,e in fit:baseline[b,s,a][e]+=1;pooled[a][e]+=1
        self.metrics={}
        for key,rows in [('validation',val),('test',test)]:
            q=self.batch(np.array([self.vector(b,s,a,r['pitcher']) for r,b,s,a,e in rows]),np.array([self.mask(a) for r,b,s,a,e in rows]));target=np.zeros_like(q)
            target[np.arange(len(rows)),[EVENTS.index(e) for r,b,s,a,e in rows]]=1
            bq=np.array([[ (baseline[b,s,a] or pooled[a])[e]/sum((baseline[b,s,a] or pooled[a]).values()) for e in EVENTS] for r,b,s,a,event in rows])
            self.metrics[key]={'baseline_brier':float(((bq-target)**2).sum(1).mean()),'pitches':len(rows),'log_loss':float(-np.log(np.maximum((q*target).sum(1),1e-12)).mean()),'brier':float(((q-target)**2).sum(1).mean())}
        if self.metrics['validation']['brier']>self.metrics['validation']['baseline_brier']+.02:raise ValueError('투구 결과 모델이 단순 빈도 기준보다 나빠 학습을 시작하지 않습니다.')
        from baseball_lab.data.compact import mlb_names
        self.evidence={'pitcher_names':{p:mlb_names().get(p,p) for p in self.pitchers},'model':'masked-softmax-pitch-world-v1','fit_pitcher_scope':'All usable fit-period pitchers train the shared world; three fit-only identities form the experimental roster. Other identities use the learned pooled feature.','fit_pitches':len(fit),'pitchers':self.pitchers,'split':self.split,'holdout_prediction':self.metrics,'excluded_turns':len(turns)-sum(len(v) for v in parsed.values()),'source_dataset_id':data['manifest']['dataset_id'],'causal_validity':'unverified observed-action association; not a physical or identified intervention model'}

    def vector(self,b,s,action,pitcher):
        return [1.,*(float(i==b*3+s) for i in range(12)),float(action=='swing'),*(float(pitcher==p) for p in self.pitchers)]
    def mask(self,action):return np.array([e in allowed(action) and e in self.supported[action] for e in EVENTS])
    def batch(self,x,mask):
        z=x@self.w;z=np.where(mask,z,-1e9);z-=z.max(axis=1,keepdims=True);q=np.exp(z);return q/q.sum(axis=1,keepdims=True)
    def pitch(self,b,s,action,pitcher,rng):
        q=self.batch(np.array([self.vector(b,s,action,pitcher)]),self.mask(action)[None,:])[0]
        return rng.choices(EVENTS,weights=q,k=1)[0]
    def advance(self,outs,bases,event,rng):
        if event in ('walk','hbp'):
            end,runs=walk(bases);return outs,end,runs
        if event=='strikeout':return outs+1,bases if outs<2 else 0,0
        if event=='home_run':return outs,0,1+bases.bit_count()
        counts=self.runner[outs,bases,event]
        if not counts:raise ValueError(f'{outs}아웃·주자{bases}·{event}의 실제 진루 전이 표본이 없습니다. 결과를 만들지 않고 중단합니다.')
        # Draw a modeled transition code from fitted frequencies, never a historical row.
        delta,end,runs=rng.choices(tuple(counts),weights=tuple(counts.values()),k=1)[0]
        return outs+delta,end,runs

@dataclass(frozen=True)
class Observation:
    inning:int;bottom:int;outs:int;bases:int;difference:int;balls:int;strikes:int;pitcher:int;faced:int
FEATURES=('bias','inning','bottom','outs','first','second','third','difference','balls','strikes','pitcher','faced')
def features(o,role):
    return np.array([1,o.inning/9,o.bottom,o.outs/2,*(int(bool(o.bases&(1<<i))) for i in range(3)),math.tanh((o.difference if role=='batter' else -o.difference)/5),o.balls/3,o.strikes/2,o.pitcher/2,min(o.faced/12,1)])
def policy(role,seed):return NeuralPolicy(role,seed,actions=OFF if role=='batter' else DEF,feature_encoder=features,feature_names=FEATURES,observation_schema=SCHEMA,action_schema='pitch-swing-and-pitcher-management-v1')


def play(world,teams,seed,record=False,home_team=1):
    order=(1-home_team,home_team);rng=Random(seed);score=[0,0];events=[];active=[0,0];used=[{0},{0}];faced=[0,0];half_ended=[True,True];counts=[Counter(),Counter()]
    for inning in range(1,19):
        for batting in (0,1):
            if batting and inning>=9 and score[1]>score[0]:return finish(score,events,counts,order)
            fielding=1-batting;outs=0;bases=2 if inning>9 else 0
            for pa in range(200):
                balls=strikes=0
                for pitch in range(100):
                    o=Observation(inning,batting,outs,bases,score[batting]-score[fielding],balls,strikes,active[fielding],faced[fielding]);legal=['pitch','intentional_walk']
                    if faced[fielding]>=3 or half_ended[fielding]:legal.extend('change_'+str(i) for i in (1,2) if i not in used[fielding])
                    b=teams[order[batting]][0].act(o,OFF,rng);p=teams[order[fielding]][1].act(o,legal,rng)
                    counts[order[batting]][b]+=1;counts[order[fielding]][p]+=1
                    if p.startswith('change_'):
                        active[fielding]=int(p[-1]);used[fielding].add(active[fielding]);faced[fielding]=0;half_ended[fielding]=False;continue
                    half_ended[fielding]=False
                    event='walk' if p=='intentional_walk' else world.pitch(balls,strikes,b,world.pitchers[active[fielding]],rng)
                    state=State(4,strikes,'walk') if event in ('walk','hbp') else transition(State(balls,strikes),event,RuleSet());terminal=state.result
                    if record:events.append({'inning':inning,'bottom':batting,'balls':balls,'strikes':strikes,'outs':outs,'bases':bases,'offense':b,'defense':p,'pitcher_id':world.pitchers[active[fielding]],'event':event,'batting_team':order[batting],'scores_before':[score[order.index(i)] for i in (0,1)]})
                    balls,strikes=state.balls,state.strikes
                    if terminal:
                        outs,bases,runs=world.advance(outs,bases,'hbp' if event=='hbp' else terminal,rng)
                        if batting and inning>=9 and score[1]+runs>score[0] and terminal!='home_run':runs=min(runs,score[0]-score[1]+1)
                        score[batting]+=runs;faced[fielding]+=1
                        if record:events[-1].update(scores=[score[order.index(i)] for i in (0,1)],runs=runs,after_outs=outs,after_bases=bases)
                        break
                else:raise RuntimeError('한 타석 100구 한도: 임의 결과 없이 중단합니다.')
                if batting and inning>=9 and score[1]>score[0]:return finish(score,events,counts,order)
                if outs>=3:half_ended[fielding]=True;break
            else:raise RuntimeError('한 이닝 안전 한도 초과')
        if inning>=9 and score[0]!=score[1]:return finish(score,events,counts,order)
    raise RuntimeError('18회 동점: 임의 승패 없이 중단합니다.')

def finish(score,events,counts,order):return {'scores':[score[order.index(i)] for i in (0,1)],'winner':order[int(score[1]>score[0])],'events':events,'choices':[dict(c) for c in counts]}


def train(data,start,end,output,config):
    config.validate();output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('기존 결과 덮어쓰기 거부')
    if data['manifest']['source_status']!='REAL_OBSERVED':raise ValueError('실제 자료가 필요합니다.')
    world=World(data);output.mkdir(parents=True,exist_ok=True)
    result={'schema':SCHEMA,'status':'RUNNING','created_at':utc_now(),'dataset':data['manifest'],'world':world.evidence,'config':asdict(config),'seeds':[],
        'reward':'team final win +1 / loss -1 only; both A and B train','limitations':['No pitch type, location, velocity or batted-ball direction is inferred.','Conditional pitch outcomes remain observational associations, not proven causal effects.','The same fit-only world is used for new-random-seed game evaluations; future pitch prediction is tested separately.','Three fit-period pitchers form a symmetric experimental roster, not an MLB club roster.','Source regular innings 1-8 are transported to late innings and extras; that transport is unvalidated.','Rules: 9 innings, walkoff, home lead skips bottom ninth, extras start runner on second, 18-inning/100-pitch safety limits abort rather than invent outcomes.','Runner transitions use fitted observed frequencies; sparse states stop rather than fabricate outcomes.']}
    import subprocess
    source_root=Path(__file__).resolve().parents[3]
    result['source_hash']=content_hash({str(p.relative_to(source_root)):p.read_text(encoding='utf-8') for p in sorted(source_root.rglob('*.py'))})
    try:result['code_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    except (OSError,subprocess.CalledProcessError):result['code_commit']='unknown'
    result['run_id']=content_hash({'schema':SCHEMA,'data':data['manifest']['dataset_id'],'config':asdict(config),'code':result['source_hash']})
    write_json(output/'world.json',{'evidence':world.evidence,'weights':world.w.tolist(),'events':EVENTS,'supported_events':{a:sorted(v) for a,v in world.supported.items()},'runner_counts':[{'outs':o,'bases':b,'event':e,'outcomes':[[*v,n] for v,n in counter.items()]} for (o,b,e),counter in world.runner.items()],'settings':{'optimizer':'minibatch gradient descent','iterations':500,'batch':1024,'learning_rate':.08,'l2':.0001,'random_seed':83}})
    for seed in config.seeds:
        teams=[(policy('batter',seed+i*2),policy('pitcher',seed+i*2+1)) for i in range(2)];initial=[[a.frozen() for a in t] for t in teams];batches=[[[],[]],[[],[]]];history=[]
        def checkpoint(done):
            for t in teams:
                for a in t:a.collect=False
            outcomes=[play(world,[[a.frozen() for a in t] for t in teams],seed+100000+i*7919,home_team=i%2) for i in range(config.evaluation_n)]
            history.append({'games':done,'A_wins':sum(g['winner']==0 for g in outcomes),'B_wins':sum(g['winner']==1 for g in outcomes),'evaluation_games':len(outcomes)})
            write_json(output/'checkpoints'/f'{seed}-{done}.json',{'schema':SCHEMA,'teams':[[a.state_dict() for a in t] for t in teams]})
            write_json(output/'research.json',result);report(output,result)
        run={'seed':seed,'history':history};result['seeds'].append(run);checkpoint(0)
        rng=Random(seed)
        for episode in range(1,config.episodes+1):
            for t in teams:
                for a in t:a.collect=True;a.decisions=[]
            game=play(world,teams,rng.randrange(2**31),home_team=episode%2)
            for i,t in enumerate(teams):
                for j,a in enumerate(t):batches[i][j].append((list(a.decisions),1 if game['winner']==i else -1))
            if episode%config.batch_size==0 or episode==config.episodes or episode%config.evaluate_every==0:
                for i,t in enumerate(teams):
                    for j,a in enumerate(t):a.update(batches[i][j]);batches[i][j]=[]
            if episode%config.evaluate_every==0 or episode==config.episodes:
                print(f'학습 {episode}/{config.episodes}경기 · A팀과 B팀이 매 공의 행동을 학습합니다.',flush=True);checkpoint(episode)
        run['replay']=play(world,[[a.frozen() for a in t] for t in teams],seed+900000,record=True)
        run['optimizer_steps']=[[a.steps for a in t] for t in teams]
        run['parameters_changed']=[[any(not np.array_equal(x,y) for x,y in zip(old.params,a.params)) for old,a in zip(initial[i],t)] for i,t in enumerate(teams)]
    result['status']='COMPLETED';write_json(output/'research.json',result);report(output,result);return result


def render(result):
    import json
    encoded=json.dumps(result,ensure_ascii=False).replace('<','\\u003c')
    return Path(__file__).with_name('results.html').read_text(encoding='utf-8').replace('__DATA__',encoded)
def report(output,result):Path(output/'report.html').write_text(render(result),encoding='utf-8')
