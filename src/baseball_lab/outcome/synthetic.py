import math
from random import Random
from baseball_lab.core.contracts import BatAction, PitchAction, PITCH_ACTIONS

class SyntheticOutcome:
    """Illustrative discrete model; not physics or empirically calibrated baseball."""
    calibration_id = "synthetic-v1"

    def probabilities(self, pitch: PitchAction, bat: BatAction) -> dict[str, float]:
        if pitch not in PITCH_ACTIONS or bat not in tuple(BatAction):
            raise ValueError("Illegal action")
        if bat == BatAction.TAKE:
            return {"strike": .9 if pitch.zone else .1, "ball": .1 if pitch.zone else .9}
        contact = {"fastball": .78, "breaking": .64, "changeup": .70}[pitch.kind]
        contact *= (1 if pitch.zone else .55) * (.78 if bat == BatAction.POWER else 1)
        power = bat == BatAction.POWER
        in_play = contact * .72
        hits = {"out": .67, "single": .16 if power else .23,
                "double": .08 if power else .06, "triple": .01,
                "home_run": .08 if power else .03}
        result = {k: in_play * v for k, v in hits.items()}
        result.update(strike=1-contact, foul=contact*.28)
        if not all(math.isfinite(p) and 0 <= p <= 1 for p in result.values()) or not math.isclose(sum(result.values()), 1):
            raise ValueError("Invalid probability distribution")
        return result

    def sample(self, pitch: PitchAction, bat: BatAction, rng: Random) -> str:
        distribution = self.probabilities(pitch, bat)
        return rng.choices(list(distribution), weights=list(distribution.values()), k=1)[0]
