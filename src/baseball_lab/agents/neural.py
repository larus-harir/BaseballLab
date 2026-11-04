"""Small two-hidden-layer neural policies, trained by terminal-win REINFORCE.

NumPy is the only learning dependency. No action targets, imitation labels or
baseball-stat rewards are supplied to the optimizer.
"""
import copy
import numpy as np

from baseball_lab.core.game import BAT_PLAYS, PITCH_PLAYS, GAME_ACTION_SCHEMA, GAME_OBSERVATION_SCHEMA

FEATURES = ('bias', 'balls', 'strikes', 'outs', 'first', 'second', 'third', 'inning',
            'score_difference', 'home_batting', 'pitcher_load', 'two_strikes', 'three_balls',
            'runner_first_before_two_outs', 'two_outs', 'tie', 'trailing', 'late')


def features(obs, role):
    difference = obs.batting_score - obs.fielding_score
    if role == 'pitcher':
        difference = -difference
    return np.array([
        1., obs.balls/3, obs.strikes/2, obs.outs/2, *map(float, obs.bases),
        min(obs.inning/obs.regulation_innings, 2), max(-1, min(1, difference/5)),
        float(obs.bottom), min(obs.pitcher_load/180, 1), float(obs.strikes == 2),
        float(obs.balls == 3), float(obs.bases[0] and obs.outs < 2), float(obs.outs == 2),
        float(difference == 0), float(difference < 0), float(obs.inning >= obs.regulation_innings),
    ], dtype=np.float64)


class NeuralPolicy:
    def __init__(self, role, seed=0, hidden=24, *, actions=None, feature_encoder=None,
                 feature_names=FEATURES, observation_schema=GAME_OBSERVATION_SCHEMA, action_schema=GAME_ACTION_SCHEMA):
        if role not in ('batter', 'pitcher'):
            raise ValueError('Unknown policy role')
        self.role = role
        self.actions = tuple(actions) if actions is not None else BAT_PLAYS if role == 'batter' else PITCH_PLAYS
        self.encoder = feature_encoder or features
        self.feature_names = tuple(feature_names)
        self.observation_schema, self.action_schema = observation_schema, action_schema
        rng = np.random.default_rng(seed)
        self.params = []
        for inputs, outputs in ((len(self.feature_names), hidden), (hidden, hidden), (hidden, len(self.actions))):
            self.params.extend([rng.normal(0, 1/np.sqrt(inputs), (inputs, outputs)), np.zeros(outputs)])
        self.m = [np.zeros_like(p) for p in self.params]
        self.v = [np.zeros_like(p) for p in self.params]
        self.steps = 0
        self.collect = False
        self.decisions = []

    def forward(self, x):
        w1, b1, w2, b2, w3, b3 = self.params
        h1 = np.tanh(x @ w1 + b1)
        h2 = np.tanh(h1 @ w2 + b2)
        logits = h2 @ w3 + b3
        logits -= np.max(logits, axis=-1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=-1, keepdims=True)
        return probs, (x, h1, h2)

    def probabilities(self, observation):
        return self.forward(self.encoder(observation, self.role)[None, :])[0][0]

    def act(self, observation, legal_actions, rng):
        if tuple(legal_actions) != self.actions:
            raise ValueError('Incompatible legal-action schema')
        x = self.encoder(observation, self.role)
        probs = self.forward(x[None, :])[0][0]
        index = rng.choices(range(len(self.actions)), weights=probs, k=1)[0]
        if self.collect:
            self.decisions.append((x, index))
        return self.actions[index]

    def gradients(self, x, actions, advantages, episode_count):
        """Exact gradient of -sum(return-baseline)*log pi(a|s) / episodes."""
        probabilities, (x, h1, h2) = self.forward(x)
        loss = -np.sum(np.log(np.maximum(probabilities[np.arange(len(actions)), actions], 1e-30))*advantages)/episode_count
        delta = probabilities.copy()
        delta[np.arange(len(actions)), actions] -= 1
        delta *= advantages[:, None]/episode_count
        w1, b1, w2, b2, w3, b3 = self.params
        g3, gb3 = h2.T @ delta, delta.sum(axis=0)
        d2 = (delta @ w3.T)*(1-h2*h2)
        g2, gb2 = h1.T @ d2, d2.sum(axis=0)
        d1 = (d2 @ w2.T)*(1-h1*h1)
        return float(loss), [x.T @ d1, d1.sum(axis=0), g2, gb2, g3, gb3]

    def update(self, episodes, learning_rate=.001):
        decisions = [(x, action, advantage) for trace, advantage in episodes for x, action in trace]
        if not decisions:
            return 0.
        x = np.stack([d[0] for d in decisions])
        actions = np.array([d[1] for d in decisions])
        advantages = np.array([d[2] for d in decisions])
        loss, grads = self.gradients(x, actions, advantages, len(episodes))
        norm = np.sqrt(sum(np.sum(g*g) for g in grads))
        scale = min(1., 5./max(float(norm), 1e-12))
        self.steps += 1
        for p, m, v, grad in zip(self.params, self.m, self.v, grads):
            grad = grad*scale
            m *= .9; m += .1*grad
            v *= .999; v += .001*grad*grad
            p -= learning_rate*(m/(1-.9**self.steps))/(np.sqrt(v/(1-.999**self.steps))+1e-8)
        if not all(np.isfinite(p).all() for p in self.params):
            raise RuntimeError('Nonfinite network weights')
        return loss

    def frozen(self):
        clone = copy.deepcopy(self)
        clone.collect = False
        clone.decisions = []
        return clone

    def state_dict(self):
        return {'role': self.role, 'parameters': [p.tolist() for p in self.params],
                'adam_m': [p.tolist() for p in self.m], 'adam_v': [p.tolist() for p in self.v], 'steps': self.steps,
                'observation_schema': self.observation_schema, 'action_schema': self.action_schema,
                'feature_names': list(self.feature_names)}

    @classmethod
    def from_state_dict(cls, data, *, actions=None, feature_encoder=None, feature_names=FEATURES,
                        observation_schema=GAME_OBSERVATION_SCHEMA, action_schema=GAME_ACTION_SCHEMA):
        if (data.get('observation_schema') != observation_schema
                or data.get('action_schema') != action_schema or data.get('feature_names') != list(feature_names)):
            raise ValueError('Incompatible neural checkpoint schema/features')
        hidden = len(data['parameters'][1])
        policy = cls(data['role'], hidden=hidden, actions=actions, feature_encoder=feature_encoder, feature_names=feature_names, observation_schema=observation_schema, action_schema=action_schema)
        for name, source in (('params', 'parameters'), ('m', 'adam_m'), ('v', 'adam_v')):
            values = [np.asarray(value, dtype=np.float64) for value in data[source]]
            if len(values) != len(policy.params) or any(a.shape != b.shape or not np.isfinite(a).all() for a, b in zip(values, policy.params)):
                raise ValueError('Invalid checkpoint tensor shape or value')
            setattr(policy, name, values)
        if type(data['steps']) is not int or data['steps'] < 0:
            raise ValueError('Invalid optimizer step')
        policy.steps = data['steps']
        return policy
