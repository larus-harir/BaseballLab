"""Synthetic model. These probabilities have not been fitted to league data."""

import math
from random import Random

from baseball_lab.core.contracts import BatAction, OutcomeContext, PitchAction, PITCH_ACTIONS, PlayerAttributes


class SyntheticOutcome:
    calibration_id = "synthetic-v1"

    def probabilities(
        self, pitch: PitchAction, bat: BatAction, *, context: OutcomeContext | None = None,
    ) -> dict[str, float]:
        if not isinstance(bat, BatAction) or pitch not in PITCH_ACTIONS:
            raise ValueError("Illegal action")
        abilities = context.attributes if context else PlayerAttributes()
        if bat == BatAction.TAKE:
            accuracy = .8 + .2 * abilities.control
            strike = accuracy if pitch.zone else 1 - accuracy
            result = {"strike": strike, "ball": 1 - strike}
        else:
            contact = {"fastball": .78, "breaking": .64, "changeup": .70}[pitch.kind]
            contact *= (.8 + .4 * abilities.contact)
            contact *= (1 if pitch.zone else .55) * (.78 if bat == BatAction.POWER else 1)
            in_play = contact * .72
            power = bat == BatAction.POWER
            homer = (.08 if power else .03) * (.5 + abilities.power)
            # Power transfers mass from singles to home runs, preserving total probability.
            hits = {"out": .67, "single": (.24 if power else .26) - homer,
                    "double": .08 if power else .06, "triple": .01, "home_run": homer}
            result = {event: in_play * prob for event, prob in hits.items()}
            result.update(strike=1-contact, foul=contact*.28)
        if (not all(math.isfinite(p) and 0 <= p <= 1 for p in result.values())
                or not math.isclose(sum(result.values()), 1)):
            raise ValueError("Invalid probability distribution")
        return result

    def sample(
        self, pitch: PitchAction, bat: BatAction, rng: Random,
        *, context: OutcomeContext | None = None,
    ) -> str:
        distribution = self.probabilities(pitch, bat, context=context)
        return rng.choices(list(distribution), weights=list(distribution.values()), k=1)[0]
