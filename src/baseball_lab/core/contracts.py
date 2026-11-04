"""Small shared contracts; league names never select engine behavior."""

from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import Protocol, TypeVar

OBSERVATION_SCHEMA = "count-v1"
ACTION_SCHEMA = "discrete-pitch-swing-v1"


def positive_integer(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


class BatAction(str, Enum):
    TAKE = "take"
    CONTACT = "contact"
    POWER = "power"


@dataclass(frozen=True)
class PitchAction:
    kind: str
    zone: bool

    def __post_init__(self):
        if self.kind not in ("fastball", "breaking", "changeup") or type(self.zone) is not bool:
            raise ValueError("Unsupported pitch kind or non-boolean zone")


PITCH_ACTIONS = tuple(
    PitchAction(kind, zone)
    for kind in ("fastball", "breaking", "changeup")
    for zone in (True, False)
)


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
        if not self.ruleset_id:
            raise ValueError("ruleset_id is required")
        positive_integer(self.balls_to_walk, "balls_to_walk")
        positive_integer(self.strikes_to_out, "strikes_to_out")


@dataclass(frozen=True)
class LeagueProfile:
    league_id: str = "synthetic_demo"
    season: str = "none"
    ruleset_id: str = "basic-pa-v1"
    calibration_id: str = "synthetic-v1"
    data_provenance: str = "Hand-authored synthetic probabilities; no real league data"
    feature_schema_version: str = OBSERVATION_SCHEMA
    source_data_version: str = "synthetic-v1"

    def __post_init__(self):
        if any(not isinstance(value, str) or not value.strip() for value in vars(self).values()):
            raise ValueError("All profile fields must be nonempty strings")


@dataclass(frozen=True)
class PlayerAttributes:
    """Dimensionless synthetic abilities in [0, 1], not measured player ratings."""

    contact: float = 0.5
    power: float = 0.5
    control: float = 0.5

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) not in (int, float) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class OutcomeContext:
    observation: Observation
    attributes: PlayerAttributes


A = TypeVar("A")


class Policy(Protocol[A]):
    def act(self, observation: Observation, legal_actions: tuple[A, ...], rng: Random) -> A: ...


class OutcomeModel(Protocol):
    calibration_id: str

    def sample(
        self, pitch: PitchAction, bat: BatAction, rng: Random,
        *, context: OutcomeContext | None = None,
    ) -> str: ...
