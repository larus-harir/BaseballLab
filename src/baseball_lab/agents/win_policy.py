"""On-policy clipped updates with a learned terminal-win value baseline.

Only completed-game wins/losses are targets. No baseball-stat reward or desired
strategy proportion enters the optimizer. Old REINFORCE checkpoints stay legacy.
"""
import copy
import numpy as np
from .neural import NeuralPolicy


class WinPolicy(NeuralPolicy):
    algorithm='terminal-win-ppo-v1'
    settings={'epochs':4,'minibatch':512,'clip':.2,'target_kl':.02,'actor_rate':.0007,'value_rate':.001,'max_gradient_norm':.5,'discount':1.0,'reward':'completed-game win +1 / loss -1 only'}
    def __init__(self,role,seed=0,hidden=24,**kwargs):
        super().__init__(role,seed,hidden,**kwargs)
        rng=np.random.default_rng(seed+17011)
        self.value_params=[rng.normal(0,1/np.sqrt(len(self.feature_names)),(len(self.feature_names),hidden)),np.zeros(hidden),np.zeros((hidden,1)),np.zeros(1)]
        self.value_m=[np.zeros_like(v) for v in self.value_params];self.value_v=[np.zeros_like(v) for v in self.value_params]
        self.value_steps=0;self.updates=0;self.rng=np.random.default_rng(seed+31013);self.last_update={}

    def values(self,x):
        w,b,out,bias=self.value_params;h=np.tanh(x@w+b)
        return (h@out+bias)[:,0],h

    def clipped_gradients(self,x,actions,advantages,old_logp,masks,clip=.2):
        probs,cache=self.forward(x);probs*=masks;probs/=probs.sum(axis=1,keepdims=True)
        chosen=np.maximum(probs[np.arange(len(x)),actions],1e-30);ratio=np.exp(np.log(chosen)-old_logp)
        active=np.where(advantages>=0,ratio<=1+clip,ratio>=1-clip)
        effective=advantages*ratio*active
        delta=probs.copy();delta[np.arange(len(x)),actions]-=1;delta*=effective[:,None]/len(x)
        delta=self.output_gradient(delta)
        _,h1,h2=cache;w1,b1,w2,b2,w3,b3=self.params
        g3,gb3=h2.T@delta,delta.sum(axis=0);d2=(delta@w3.T)*(1-h2*h2)
        g2,gb2=h1.T@d2,d2.sum(axis=0);d1=(d2@w2.T)*(1-h1*h1)
        loss=-np.mean(np.minimum(ratio*advantages,np.clip(ratio,1-clip,1+clip)*advantages))
        return float(loss),[x.T@d1,d1.sum(axis=0),g2,gb2,g3,gb3],float(np.mean(~active))

    def output_gradient(self,delta):return delta

    @staticmethod
    def adam(params,m,v,grads,step,rate):
        norm=np.sqrt(sum(np.sum(g*g) for g in grads));scale=min(1.,.5/max(float(norm),1e-12))
        for p,first,second,g in zip(params,m,v,grads):
            g=g*scale;first*=.9;first+=.1*g;second*=.999;second+=.001*g*g
            p-=rate*(first/(1-.9**step))/(np.sqrt(second/(1-.999**step))+1e-8)

    def update(self,episodes,learning_rate=.0007):
        rows=[(d,reward) for trace,reward in episodes for d in trace]
        if not rows:return 0.
        x=np.stack([d[0] for d,r in rows]);actions=np.array([d[1] for d,r in rows]);masks=np.stack([d[2] for d,r in rows])
        returns=np.array([r for d,r in rows],dtype=float)
        old=self.forward(x)[0]*masks;old/=old.sum(axis=1,keepdims=True)
        old_logp=np.log(np.maximum(old[np.arange(len(x)),actions],1e-30));old_values,_=self.values(x)
        advantages=returns-old_values
        advantages=(advantages-advantages.mean())/max(float(advantages.std()),1e-8)
        before=[p.copy() for p in self.params];loss=clip_fraction=0.;used=0;kl=0.
        # Reuse the rollout with clipped, bounded on-policy steps. A new rollout
        # supplies fresh exploration after every update; no replay of stale games.
        for epoch in range(4):
            for indices in np.array_split(self.rng.permutation(len(x)),max(1,(len(x)+511)//512)):
                loss,grads,clip_fraction=self.clipped_gradients(x[indices],actions[indices],advantages[indices],old_logp[indices],masks[indices])
                self.steps+=1;used+=1;self.adam(self.params,self.m,self.v,grads,self.steps,learning_rate)
                values,h=self.values(x[indices]);residual=(values-returns[indices])/len(indices)
                out=self.value_params[2];delta=residual[:,None];dh=(delta@out.T)*(1-h*h)
                vgrads=[x[indices].T@dh,dh.sum(axis=0),h.T@delta,delta.sum(axis=0)]
                self.value_steps+=1;self.adam(self.value_params,self.value_m,self.value_v,vgrads,self.value_steps,.001)
            current=self.forward(x)[0]*masks;current/=current.sum(axis=1,keepdims=True)
            kl=float(np.mean(np.sum(old*(np.log(np.maximum(old,1e-30))-np.log(np.maximum(current,1e-30))),axis=1)))
            if kl>.02:break
        self.updates+=1;variance=float(np.var(returns))
        self.last_update={'rollout_games':len(episodes),'decisions':len(rows),'optimizer_steps':used,'policy_kl':kl,
            'clip_fraction':clip_fraction,'value_error_before':float(np.mean((returns-old_values)**2)),
            'value_explained_variance_before':1-float(np.var(returns-old_values))/variance if variance else None,
            'parameter_delta':float(np.sqrt(sum(np.sum((a-b)**2) for a,b in zip(self.params,before))))}
        signals={}
        for j,a in enumerate(self.actions):
            if not isinstance(a,str):continue
            keys=([('family',a.split(':')[1]),('course',a.split(':')[2])] if a.startswith('pitch:') else [('offense','swing' if a.startswith('swing:') else 'steal' if a.startswith('steal_') else a)] if self.role=='batter' else [('defense',a)])
            if a.startswith('swing:'):keys.append(('direction',a.split(':')[1]))
            chosen=actions==j
            for group,key in keys:
                if key=='any':continue
                v=signals.setdefault(group+':'+key,{'decisions':0,'wins':0,'advantage_sum':0.})
                v['decisions']+=int(chosen.sum());v['wins']+=int(np.sum(returns[chosen]>0));v['advantage_sum']+=float(advantages[chosen].sum())
        self.last_update['choice_signals']=signals
        if not all(np.isfinite(p).all() for p in (*self.params,*self.value_params)):raise RuntimeError('Nonfinite win-policy parameters')
        return loss

    def synchronize(self,other):
        for name in ('params','m','v','value_params','value_m','value_v'):setattr(self,name,[v.copy() for v in getattr(other,name)])
        for name in ('steps','value_steps','updates'):setattr(self,name,getattr(other,name))
        self.last_update=copy.deepcopy(other.last_update);self.rng.bit_generator.state=copy.deepcopy(other.rng.bit_generator.state)

    def state_dict(self):
        return {**super().state_dict(),'algorithm':self.algorithm,'optimizer_settings':dict(self.settings),'actions':list(self.actions),
            **{name:[v.tolist() for v in getattr(self,name)] for name in ('value_params','value_m','value_v')},
            'value_steps':self.value_steps,'updates':self.updates,'rng_state':copy.deepcopy(self.rng.bit_generator.state)}

    @classmethod
    def from_state_dict(cls,data,**kwargs):
        if data.get('algorithm')!=cls.algorithm:raise ValueError('Incompatible win-policy algorithm')
        p=super().from_state_dict(data,**kwargs)
        if tuple(data.get('actions',()))!=p.actions:raise ValueError('Checkpoint action order differs')
        for name in ('value_params','value_m','value_v'):
            values=[np.asarray(v,dtype=float) for v in data[name]]
            if len(values)!=len(p.value_params) or any(a.shape!=b.shape or not np.isfinite(a).all() for a,b in zip(values,p.value_params)):raise ValueError('Invalid value checkpoint')
            setattr(p,name,values)
        for name in ('value_steps','updates'):
            value=data[name]
            if type(value) is not int or value<0:raise ValueError('Invalid value optimizer step')
            setattr(p,name,value)
        p.rng.bit_generator.state=copy.deepcopy(data['rng_state']);return p


class PitchWinPolicy(WinPolicy):
    """Joint-action residuals plus shared pitch-family/course/speed logits.

    All original joint choices remain. Shared factors transfer win gradients
    across compatible choices, without targets, outcome bonuses or new evidence.
    """
    algorithm='terminal-win-ppo-shared-pitch-v1'
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        factors={}
        for i,a in enumerate(self.actions):
            if a.startswith('pitch:'):
                for kind,value in zip(('family','course','speed'),a.split(':')[1:]):factors.setdefault(kind+':'+value,[]).append(i)
        self.factor_labels=tuple(sorted(factors));self.factor_columns=[np.array(factors[k]) for k in self.factor_labels]
        self.factor_indices=np.full((len(self.actions),3),len(self.actions)+len(factors),dtype=int)
        for i,(label,columns) in enumerate(zip(self.factor_labels,self.factor_columns)):
            self.factor_indices[columns,('family','course','speed').index(label.split(':')[0])]=len(self.actions)+i
        self.params[-2]=np.pad(self.params[-2],((0,0),(0,len(factors))));self.params[-1]=np.pad(self.params[-1],(0,len(factors)))
        self.m=[np.zeros_like(v) for v in self.params];self.v=[np.zeros_like(v) for v in self.params]

    def forward(self,x):
        w1,b1,w2,b2,w3,b3=self.params;h1=np.tanh(x@w1+b1);h2=np.tanh(h1@w2+b2);raw=h2@w3+b3
        logits=raw[:,:len(self.actions)].copy()
        logits+=np.pad(raw,((0,0),(0,1)))[:,self.factor_indices].sum(axis=2)/np.sqrt(3.)
        logits-=np.max(logits,axis=-1,keepdims=True);probs=np.exp(logits);probs/=probs.sum(axis=-1,keepdims=True)
        return probs,(x,h1,h2)

    def output_gradient(self,delta):
        return np.concatenate((delta,np.stack([delta[:,c].sum(axis=1)/np.sqrt(3.) for c in self.factor_columns],axis=1)),axis=1)

    def state_dict(self):return {**super().state_dict(),'pitch_factors':list(self.factor_labels),'joint_residuals':True}

    @classmethod
    def from_state_dict(cls,data,**kwargs):
        p=super().from_state_dict(data,**kwargs)
        if data.get('pitch_factors')!=list(p.factor_labels) or data.get('joint_residuals') is not True:raise ValueError('Incompatible shared pitch factors')
        return p
