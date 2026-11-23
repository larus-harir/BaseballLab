"""MOCK_TEST_ONLY terminal-win environments, never production observations."""
from copy import deepcopy
from random import Random
import numpy as np
import pytest
from baseball_lab.agents.win_policy import WinPolicy


def encode(state,role):return np.array([1.,float(state)])


def policy(seed=4,hidden=8):
    p=WinPolicy('batter',seed,hidden,actions=('MOCK_TEST_ONLY_left','MOCK_TEST_ONLY_right'),feature_encoder=encode,
                feature_names=('bias','MOCK_TEST_ONLY_context'),observation_schema='MOCK_TEST_ONLY',action_schema='MOCK_TEST_ONLY')
    p.params[-2].fill(0.)
    return p


def test_clipped_surrogate_gradient_matches_numerical_derivative():
    p=policy(hidden=4);p.params[-2][:]=np.random.default_rng(21).normal(0,.1,p.params[-2].shape);x=np.array([[1.,-1.],[1.,1.],[1.,.5],[1.,-.5]])
    a=np.array([0,1,0,1]);adv=np.array([1.,-1.,.5,-.4]);masks=np.ones((4,2),dtype=bool)
    q=p.forward(x)[0];old=np.log(q[np.arange(4),a])-np.log([1.4,.6,1.1,.9])
    loss,grads,clipped=p.clipped_gradients(x,a,adv,old,masks)
    assert clipped==.5
    for tensor,grad in zip(p.params,grads):
        index=tuple(0 for _ in tensor.shape);v=tensor[index];epsilon=1e-5
        tensor[index]=v+epsilon;plus=p.clipped_gradients(x,a,adv,old,masks)[0]
        tensor[index]=v-epsilon;minus=p.clipped_gradients(x,a,adv,old,masks)[0];tensor[index]=v
        assert grad[index]==pytest.approx((plus-minus)/(2*epsilon),abs=1e-7)


def learn(p,rounds,seed,invert=False):
    rng=Random(seed)
    for _ in range(rounds):
        episodes=[]
        for i in range(64):
            state=-1 if i%2 else 1;p.collect=True;p.decisions=[]
            action=p.act(state,p.actions,rng)
            wins=(action==p.actions[int(state>0)]) != invert
            episodes.append((list(p.decisions),1. if wins else -1.))
        p.update(episodes,learning_rate=.003)


def test_terminal_wins_learn_context_and_reversing_winners_changes_preference():
    p=policy();learn(p,80,14)
    initial=sum(p.probabilities(s)[int(s>0)] for s in (-1,1))/2
    assert initial>.85
    learn(p,160,51,invert=True)
    reversed_rate=sum(p.probabilities(s)[int(s<0)] for s in (-1,1))/2
    assert reversed_rate>.8
    assert p.updates==240 and p.last_update['parameter_delta']>0
    assert p.last_update['policy_kl']>=-1e-12


def test_critic_and_optimizer_roundtrip_and_action_order_validation():
    p=policy();learn(p,3,52);d=p.state_dict();original=deepcopy(d)
    kwargs={'actions':p.actions,'feature_encoder':encode,'feature_names':p.feature_names,'observation_schema':'MOCK_TEST_ONLY','action_schema':'MOCK_TEST_ONLY'}
    loaded=WinPolicy.from_state_dict(d,**kwargs)
    assert loaded.state_dict()==d and d==original
    for s in (-1,1):assert np.array_equal(loaded.probabilities(s),p.probabilities(s))
    with pytest.raises(ValueError):WinPolicy.from_state_dict(d,**{**kwargs,'actions':tuple(reversed(p.actions))})
    bad=deepcopy(d);bad['value_steps']=-1
    with pytest.raises(ValueError):WinPolicy.from_state_dict(bad,**kwargs)
    bad=deepcopy(d);bad['value_params'][0][0][0]=float('nan')
    with pytest.raises(ValueError):WinPolicy.from_state_dict(bad,**kwargs)
    clone=policy(seed=52);clone.synchronize(p)
    assert clone.state_dict()==p.state_dict()


def test_no_reward_signal_does_not_force_a_favored_action():
    p=policy();rng=Random(74);episodes=[]
    before=[v.copy() for v in p.params]
    for i in range(64):
        p.collect=True;p.decisions=[];p.act((-1,1)[i%2],p.actions,rng)
        episodes.append((list(p.decisions),0.))
    p.update(episodes)
    assert all(np.array_equal(a,b) for a,b in zip(before,p.params))
    assert p.last_update['parameter_delta']==0 and p.last_update['policy_kl']==0
