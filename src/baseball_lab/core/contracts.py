from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import Protocol, TypeVar

OBSERVATION_SCHEMA = "count-v1"
ACTION_SCHEMA = "discrete-pitch-swing-v1"

class BatAction(str, Enum):
    TAKE = "take"
    CONTACT = "contact"
    POWER = "power"

@dataclass(frozen=True)
class PitchAction:
    kind: str
    zone: bool

PITCH_ACTIONS = tuple(PitchAction(k, z) for k in ("fastball", "breaking", "changeup") for z in (True, False))

@dataclass(frozen=True)
class Observation:
    balls: int
    strikes: int
    # Deliberately excludes the current pitch and any future outcome.

@dataclass(frozen=True)
class RuleSet:
    ruleset_id: str = "basic-pa-v1"
    balls_to_walk: int = 4
    strikes_to_out: int = 3

    def __post_init__(self):
        if self.balls_to_walk < 1 or self.strikes_to_out < 1:
            raise ValueError("Count thresholds must be positive")

@dataclass(frozen=True)
class LeagueProfile:
    league_id: str = "synthetic_demo"
    season: str = "none"
    ruleset_id: str = "basic-pa-v1"
    calibration_id: str = "synthetic-v1"
    data_provenance: str = "Hand-authored synthetic probabilities; no real league data"
    feature_schema_version: str = OBSERVATION_SCHEMA

A = TypeVar("A")
class Policy(Protocol[A]):
    def act(self, observation: Observation, legal_actions: tuple[A, ...], rng: Random) -> A: ...

class OutcomeModel(Protocol):
    calibration_id: str
    def sample(self, pitch: PitchAction, bat: BatAction, rng: Random) -> str: ...
