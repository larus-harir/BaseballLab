from dataclasses import dataclass
from random import Random
from baseball_lab.core.contracts import BatAction, Observation, PitchAction

BATTERS = ("random", "aggressive", "patient")
PITCHERS = ("random", "strike_first", "mixed")

@dataclass(frozen=True)
class Batter:
    name: str
    def __post_init__(self):
        if self.name not in BATTERS:
            raise ValueError("Unknown batter")
    def act(self, observation: Observation, legal_actions: tuple[BatAction, ...], rng: Random) -> BatAction:
        if self.name == "random":
            return rng.choice(legal_actions)
        if self.name == "aggressive":
            return rng.choice((BatAction.CONTACT, BatAction.POWER))
        return BatAction.CONTACT if observation.strikes >= 2 else BatAction.TAKE

@dataclass(frozen=True)
class Pitcher:
    name: str
    def __post_init__(self):
        if self.name not in PITCHERS:
            raise ValueError("Unknown pitcher")
    def act(self, observation: Observation, legal_actions: tuple[PitchAction, ...], rng: Random) -> PitchAction:
        if self.name == "random":
            return rng.choice(legal_actions)
        if self.name == "strike_first":
            return PitchAction("fastball", True)
        return PitchAction(rng.choice(("fastball", "breaking", "changeup")), rng.random() < .65)
