"""Bounded synthetic abilities, command/effort/fatigue and sacrifice-bunt outcomes."""
from random import Random

from baseball_lab.core.contracts import BatAction, OutcomeContext, PitchAction, PlayerAttributes
from baseball_lab.core.game import BatPlay, GameObservation, PitchPlay
from .synthetic import SyntheticOutcome


class GameOutcome:
    calibration_id = 'synthetic-game-v1'

    def __init__(self, attributes: PlayerAttributes = PlayerAttributes()):
        self.attributes = attributes
        self.base = SyntheticOutcome()

    def sample(self, obs: GameObservation, pitch: PitchPlay, bat: BatPlay, rng: Random) -> str:
        fatigue = min(obs.pitcher_load / 180, 1.0)
        control = max(0., min(1., self.attributes.control - .12*pitch.effort - .4*fatigue))
        accuracy = .70 + .28*control
        actual_zone = pitch.zone if rng.random() < accuracy else not pitch.zone
        if bat == BatPlay.BUNT:
            contact = .80 if actual_zone else .35
            roll = rng.random()
            if roll > contact:
                return 'strike'
            relative = roll/contact
            if relative < .20:
                return 'strike' if obs.strikes >= 2 else 'foul'
            return 'bunt_out' if relative < .85 else 'single'
        ability = max(0., min(1., self.attributes.contact + .45*fatigue - .15*pitch.effort))
        attributes = PlayerAttributes(ability, self.attributes.power, 1.)
        context = OutcomeContext(obs, attributes)
        event = self.base.sample(PitchAction(pitch.kind, actual_zone), BatAction(bat.value), rng, context=context)
        if event == 'out' and rng.random() < .5:
            return 'ground_out'
        return event
