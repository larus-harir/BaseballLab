"""Shared inning/base/score engine over the existing plate-appearance rules."""
from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import Callable

from .contracts import LeagueProfile, Observation, RuleSet, positive_integer
from .engine import State, transition

GAME_OBSERVATION_SCHEMA = 'game-public-v1'
GAME_ACTION_SCHEMA = 'game-bat4-pitch18-v1'


class BatPlay(str, Enum):
    TAKE = 'take'
    CONTACT = 'contact'
    POWER = 'power'
    BUNT = 'bunt'


@dataclass(frozen=True)
class PitchPlay:
    kind: str
    zone: bool
    effort: int


BAT_PLAYS = tuple(BatPlay)
PITCH_PLAYS = tuple(PitchPlay(k, z, e) for k in ('fastball', 'breaking', 'changeup')
                    for z in (True, False) for e in (-1, 0, 1))


@dataclass(frozen=True)
class GameObservation(Observation):
    inning: int
    regulation_innings: int
    outs: int
    bases: tuple[bool, bool, bool]
    batting_score: int
    fielding_score: int
    bottom: bool
    pitcher_load: float


@dataclass(frozen=True)
class GameRules:
    innings: int = 3
    max_extra_innings: int = 2
    max_plate_appearances_per_half: int = 300

    def __post_init__(self):
        positive_integer(self.innings, 'innings')
        positive_integer(self.max_plate_appearances_per_half, 'max_plate_appearances_per_half')
        if type(self.max_extra_innings) is not int or self.max_extra_innings < 0:
            raise ValueError('max_extra_innings must be a nonnegative integer')


def advance(bases: tuple[bool, bool, bool], result: str, outs: int,
            rng: Random) -> tuple[tuple[bool, bool, bool], int, int]:
    """Return bases, runs, outs added. Conservative, explicit running assumptions."""
    if result == 'walk':
        first, second, third = bases
        return (True, first or second, third or (first and second)), int(all(bases)), 0
    if result in ('single', 'double', 'triple', 'home_run'):
        distance = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}[result]
        runners = [index+1 for index, occupied in enumerate(bases) if occupied] + [0]
        destinations = [base + distance for base in runners]
        return tuple(base in destinations for base in (1, 2, 3)), sum(base > 3 for base in destinations), 0
    if result == 'bunt_out' and outs < 2:
        return (False, bases[0], bases[1]), int(bases[2]), 1
    if result == 'ground_out' and bases[0] and outs < 2 and rng.random() < .35:
        return (False, bases[1], bases[2]), 0, 2
    if result in ('out', 'bunt_out', 'ground_out', 'strikeout'):
        return bases, 0, 1
    raise ValueError(f'Unknown terminal event: {result}')


@dataclass
class Team:
    name: str
    batter: object
    pitcher: object


@dataclass
class GameResult:
    away_score: int
    home_score: int
    innings_played: int
    pitches: int
    events: list[dict]

    @property
    def winner(self):
        return 0 if self.away_score > self.home_score else 1 if self.home_score > self.away_score else None

    def reward(self, team: int) -> int:
        if team not in (0, 1):
            raise ValueError('team must be away=0 or home=1')
        return 0 if self.winner is None else 1 if self.winner == team else -1


class GameEngine:
    def __init__(self, outcome, rules: GameRules = GameRules(), pa_rules: RuleSet = RuleSet(),
                 profile: LeagueProfile | None = None):
        self.profile = profile or LeagueProfile(ruleset_id=pa_rules.ruleset_id,
            calibration_id=outcome.calibration_id, feature_schema_version=GAME_OBSERVATION_SCHEMA,
            source_data_version=outcome.calibration_id)
        if (self.profile.feature_schema_version != GAME_OBSERVATION_SCHEMA
                or self.profile.ruleset_id != pa_rules.ruleset_id
                or self.profile.calibration_id != outcome.calibration_id):
            raise ValueError('Incompatible game profile, rules or outcome model')
        self.outcome, self.rules, self.pa_rules = outcome, rules, pa_rules

    def play(self, away: Team, home: Team, seed: int, *, record: bool = False,
             event_sink: Callable[[dict], None] | None = None) -> GameResult:
        teams = (away, home)
        rngs = {role: Random(f'game-v1:{seed}:{role}') for role in ('away-bat', 'home-bat', 'away-pitch', 'home-pitch', 'outcome', 'running')}
        scores, loads, events = [0, 0], [0.0, 0.0], []
        total_pitches = 0
        for inning in range(1, self.rules.innings + self.rules.max_extra_innings + 1):
            for batting in (0, 1):
                fielding = 1 - batting
                if batting == 1 and inning >= self.rules.innings and scores[1] > scores[0]:
                    return GameResult(*scores, inning, total_pitches, events)
                bases, outs = (False, False, False), 0
                for pa in range(1, self.rules.max_plate_appearances_per_half + 1):
                    state = State()
                    for pitch_number in range(1, 1001):
                        observation = GameObservation(state.balls, state.strikes, inning, self.rules.innings,
                                                      outs, bases, scores[batting], scores[fielding], batting == 1, loads[fielding])
                        bat = teams[batting].batter.act(observation, BAT_PLAYS, rngs['away-bat' if batting == 0 else 'home-bat'])
                        pitch = teams[fielding].pitcher.act(observation, PITCH_PLAYS, rngs['away-pitch' if fielding == 0 else 'home-pitch'])
                        if not isinstance(bat, BatPlay) or not isinstance(pitch, PitchPlay) or pitch not in PITCH_PLAYS:
                            raise ValueError('Illegal game action')
                        event = self.outcome.sample(observation, pitch, bat, rngs['outcome'])
                        state = transition(state, event, self.pa_rules)
                        loads[fielding] += { -1: .7, 0: 1., 1: 1.5 }[pitch.effort]
                        total_pitches += 1
                        runs = added_outs = 0
                        if state.result is not None:
                            bases, runs, added_outs = advance(bases, state.result, outs, rngs['running'])
                            scores[batting] += runs
                            outs += added_outs
                        if record or event_sink is not None:
                            row = {
                                'inning': inning, 'bottom': batting == 1, 'plate_appearance': pa,
                                'pitch_number': pitch_number, 'balls': observation.balls, 'strikes': observation.strikes,
                                'outs_before': observation.outs, 'bases_before': list(observation.bases),
                                'batter_action': bat.value, 'pitch_type': pitch.kind, 'target_zone': pitch.zone,
                                'effort': pitch.effort, 'event': event, 'result': state.result,
                                'runs': runs, 'outs_after': outs, 'bases_after': list(bases),
                                'away_score': scores[0], 'home_score': scores[1],
                            }
                            if record:
                                events.append(row)
                            if event_sink is not None:
                                event_sink(row)
                        if inning >= self.rules.innings and batting == 1 and scores[1] > scores[0]:
                            return GameResult(*scores, inning, total_pitches, events)
                        if state.result is not None:
                            break
                    else:
                        raise RuntimeError('Pitch safety limit reached; no reward assigned')
                    if outs >= 3:
                        break
                else:
                    raise RuntimeError('Half-inning safety limit reached; no reward assigned')
            if inning >= self.rules.innings and scores[0] != scores[1]:
                return GameResult(*scores, inning, total_pitches, events)
        return GameResult(*scores, inning, total_pitches, events)
