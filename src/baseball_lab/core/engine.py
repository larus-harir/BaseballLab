from dataclasses import dataclass
from random import Random
from .contracts import (ACTION_SCHEMA, OBSERVATION_SCHEMA, BatAction, LeagueProfile,
                        Observation, OutcomeModel, PITCH_ACTIONS, Policy, PitchAction, RuleSet)

@dataclass(frozen=True)
class State:
    balls: int = 0
    strikes: int = 0
    result: str | None = None

def transition(state: State, event: str, rules: RuleSet) -> State:
    if state.result is not None:
        raise ValueError("Plate appearance already finished")
    if not (0 <= state.balls < rules.balls_to_walk and 0 <= state.strikes < rules.strikes_to_out):
        raise ValueError("Invalid count")
    if event == "ball":
        return State(state.balls + 1, state.strikes, "walk" if state.balls + 1 == rules.balls_to_walk else None)
    if event == "strike":
        return State(state.balls, state.strikes + 1, "strikeout" if state.strikes + 1 == rules.strikes_to_out else None)
    if event == "foul":
        return State(state.balls, min(state.strikes + 1, rules.strikes_to_out - 1))
    if event in ("out", "single", "double", "triple", "home_run"):
        return State(state.balls, state.strikes, event)
    raise ValueError(f"Unknown event: {event}")

@dataclass(frozen=True)
class PitchRecord:
    observation: Observation
    pitch: PitchAction
    bat: BatAction
    event: str

class Engine:
    def __init__(self, rules: RuleSet, profile: LeagueProfile, outcome: OutcomeModel):
        if profile.ruleset_id != rules.ruleset_id:
            raise ValueError("Profile/ruleset mismatch")
        if profile.feature_schema_version != OBSERVATION_SCHEMA:
            raise ValueError("Unsupported observation schema")
        if profile.calibration_id != outcome.calibration_id:
            raise ValueError("Profile/calibration mismatch")
        self.rules, self.profile, self.outcome = rules, profile, outcome

    def play(self, batter: Policy[BatAction], pitcher: Policy[PitchAction],
             batter_rng: Random, pitcher_rng: Random, outcome_rng: Random,
             max_pitches: int = 1000) -> tuple[State, list[PitchRecord]]:
        state, records = State(), []
        for _ in range(max_pitches):
            obs = Observation(state.balls, state.strikes)
            # Both policies receive only the same public pre-pitch count.
            bat = batter.act(obs, tuple(BatAction), batter_rng)
            pitch = pitcher.act(obs, PITCH_ACTIONS, pitcher_rng)
            if bat not in tuple(BatAction) or pitch not in PITCH_ACTIONS:
                raise ValueError("Illegal action")
            event = self.outcome.sample(pitch, bat, outcome_rng)
            records.append(PitchRecord(obs, pitch, bat, event))
            state = transition(state, event, self.rules)
            if state.result is not None:
                return state, records
        raise RuntimeError("Pitch safety limit reached; no artificial result assigned")
