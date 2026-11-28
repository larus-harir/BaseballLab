"""MOCK_TEST_ONLY reward experiments; never production baseball evidence."""
from random import Random
import numpy as np
import pytest
from baseball_lab.agents.win_policy import PitchCreditPolicy, PitchWinPolicy


def policy(policy_type=PitchWinPolicy):
    actions=tuple(f'pitch:{f}:{c}:fast' for f in ('fastball','slider') for c in ('left_low','left_high'))
    p=policy_type('pitcher',4,8,actions=actions,feature_names=('MOCK_TEST_ONLY_bias',),feature_encoder=lambda o,r:np.ones(1),observation_schema='MOCK_TEST_ONLY',action_schema='MOCK_TEST_ONLY')
    p.params[-2].fill(0.);return p


def train(p,low=True):
    rng=Random(51)
    for _ in range(70):
        batch=[]
        for i in range(48):
            p.collect=True;p.decisions=[];a=p.act(None,p.actions[:2],rng)
            batch.append((list(p.decisions),1. if ('left_low' in a)==low else -1.))
        p.update(batch,learning_rate=.003)


@pytest.mark.parametrize('policy_type',(PitchWinPolicy,PitchCreditPolicy))
def test_course_win_signal_transfers_between_families_and_joint_choices_survive(policy_type):
    p=policy(policy_type);train(p)
    assert p.probabilities(None,p.actions[:2])[0]>.8
    assert p.probabilities(None,p.actions[2:])[2]>.6
    train(p,low=False)
    assert p.probabilities(None,p.actions[2:])[3]>.6
    assert p.params[-2].shape[1]>len(p.actions) # individual residuals remain


@pytest.mark.parametrize('policy_type',(PitchWinPolicy,PitchCreditPolicy))
def test_shared_and_joint_head_gradients_and_checkpoint_restore(policy_type):
    p=policy(policy_type);p.params[-2][:]=np.random.default_rng(12).normal(0,.1,p.params[-2].shape)
    x=np.ones((4,1));actions=np.array([0,1,2,3]);advantages=np.array([1.,-1.,.3,-.5]);masks=np.ones((4,4),dtype=bool)
    old=np.log(p.forward(x)[0][np.arange(4),actions]);loss,grads,_=p.clipped_gradients(x,actions,advantages,old,masks)
    for tensor,grad in zip(p.params,grads):
        index=tuple(s-1 for s in tensor.shape);original=tensor[index];eps=1e-5
        tensor[index]=original+eps;hi=p.clipped_gradients(x,actions,advantages,old,masks)[0]
        tensor[index]=original-eps;lo=p.clipped_gradients(x,actions,advantages,old,masks)[0];tensor[index]=original
        assert grad[index]==pytest.approx((hi-lo)/(2*eps),abs=1e-7)
    train(p);d=p.state_dict();loaded=policy_type.from_state_dict(d,actions=p.actions,feature_names=p.feature_names,feature_encoder=p.encoder,observation_schema='MOCK_TEST_ONLY',action_schema='MOCK_TEST_ONLY')
    assert loaded.state_dict()==d
    assert np.array_equal(loaded.probabilities(None),p.probabilities(None))
