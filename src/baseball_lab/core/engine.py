"""Plate-appearance rules, independent of any experiment or league calibration."""

from dataclasses import dataclass
from random import Random

from .contracts import (
    OBSERVATION_SCHEMA, BatAction, LeagueProfile, Observation, OutcomeContext,
    OutcomeModel, PITCH_ACTIONS, PitchAction, PlayerAttributes, Policy, RuleSet,
    positive_integer,
)

TERMINAL_RESULTS = ("walk", "strikeout", "out", "single", "double", "triple", "home_run")


@dataclass(frozen=True)
class State:
    balls: int = 0
    strikes: int = 0
    result: str | None = None


def transition(state: State, event: str, rules: RuleSet) -> State:
    if state.result is not None:
        raise ValueError("Plate appearance already finished")
    if (type(state.balls) is not int or type(state.strikes) is not int
            or not 0 <= state.balls < rules.balls_to_walk
            or not 0 <= state.strikes < rules.strikes_to_out):
        raise ValueError("Invalid count")
    if event == "ball":
        balls = state.balls + 1
        return State(balls, state.strikes, "walk" if balls == rules.balls_to_walk else None)
    if event == "strike":
        strikes = state.strikes + 1
        return State(state.balls, strikes, "strikeout" if strikes == rules.strikes_to_out else None)
    if event == "foul":
        return State(state.balls, min(state.strikes + 1, rules.strikes_to_out - 1))
    if event in TERMINAL_RESULTS[2:]:
        return State(state.balls, state.strikes, event)
    raise ValueError(f"Unknown event: {event}")


@dataclass(frozen=True)
class PitchRecord:
    observation: Observation
    pitch: PitchAction
    bat: BatAction
    event: str


class Engine:
    def __init__(
        self, rules: RuleSet, profile: LeagueProfile, outcome: OutcomeModel,
        attributes: PlayerAttributes = PlayerAttributes(),
    ):
        if profile.ruleset_id != rules.ruleset_id:
            raise ValueError("Profile/ruleset mismatch")
        if profile.feature_schema_version != OBSERVATION_SCHEMA:
            raise ValueError("Unsupported observation schema")
        if profile.calibration_id != outcome.calibration_id:
            raise ValueError("Profile/calibration mismatch")
        self.rules, self.profile, self.outcome = rules, profile, outcome
        self.attributes = attributes

    def play(
        self, batter: Policy[BatAction], pitcher: Policy[PitchAction],
        batter_rng: Random, pitcher_rng: Random, outcome_rng: Random,
        max_pitches: int = 1000,
    ) -> tuple[State, list[PitchRecord]]:
        positive_integer(max_pitches, "max_pitches")
        state, records = State(), []
        for _ in range(max_pitches):
            obs = Observation(state.balls, state.strikes)
            bat = batter.act(obs, tuple(BatAction), batter_rng)
            pitch = pitcher.act(obs, PITCH_ACTIONS, pitcher_rng)
            if not isinstance(bat, BatAction) or not isinstance(pitch, PitchAction) or pitch not in PITCH_ACTIONS:
                raise ValueError("Illegal action")
            event = self.outcome.sample(
                pitch, bat, outcome_rng,
                context=OutcomeContext(obs, self.attributes),
            )
            records.append(PitchRecord(obs, pitch, bat, event))
            state = transition(state, event, self.rules)
            if state.result is not None:
                return state, records
        raise RuntimeError("Pitch safety limit reached; no artificial result assigned")
