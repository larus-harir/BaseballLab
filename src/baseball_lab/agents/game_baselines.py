"""Comparison opponents only; their heuristics never enter the learning reward."""
from baseball_lab.core.game import BatPlay, PitchPlay


class GameBaseline:
    def __init__(self, role: str, style: str = 'random'):
        if role not in ('batter', 'pitcher') or style not in ('random', 'aggressive', 'patient', 'mixed', 'strike_first'):
            raise ValueError('Unknown role/style')
        self.role, self.style = role, style

    def act(self, obs, legal_actions, rng):
        if self.style == 'random':
            return rng.choice(legal_actions)
        if self.role == 'batter':
            if self.style == 'aggressive':
                return rng.choice((BatPlay.CONTACT, BatPlay.POWER))
            return BatPlay.TAKE if obs.strikes < 2 else BatPlay.CONTACT
        if self.style == 'strike_first':
            return PitchPlay('fastball', True, 0)
        return PitchPlay(rng.choice(('fastball', 'breaking', 'changeup')), rng.random() < .65, rng.choice((-1, 0, 1)))
