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
        _,h1,h2=cache;w1,b1,w2,b2,w3,b3=self.params
        g3,gb3=h2.T@delta,delta.sum(axis=0);d2=(delta@w3.T)*(1-h2*h2)
        g2,gb2=h1.T@d2,d2.sum(axis=0);d1=(d2@w2.T)*(1-h1*h1)
        loss=-np.mean(np.minimum(ratio*advantages,np.clip(ratio,1-clip,1+clip)*advantages))
        return float(loss),[x.T@d1,d1.sum(axis=0),g2,gb2,g3,gb3],float(np.mean(~active))

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
