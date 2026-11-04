from collections import Counter
from dataclasses import asdict, dataclass
from random import Random
from baseball_lab.agents.baselines import Batter, Pitcher
from baseball_lab.core.engine import Engine

@dataclass(frozen=True)
class MatchSpec:
    batter: str
    pitcher: str
    seed: int
    plate_appearances: int
    def __post_init__(self):
        if self.plate_appearances < 1:
            raise ValueError("plate_appearances must be positive")

def evaluate(engine: Engine, spec: MatchSpec) -> dict:
    batter, pitcher = Batter(spec.batter), Pitcher(spec.pitcher)
    # Independent streams prevent one policy's random draw count from changing the other's.
    streams = [Random(spec.seed * 3 + i) for i in range(3)]
    results, actions, kinds, zones, counts = (Counter() for _ in range(5))
    first_swings = first_strikes = pitches = 0
    for _ in range(spec.plate_appearances):
        final, records = engine.play(batter, pitcher, *streams)
        results[final.result] += 1
        first_swings += records[0].bat.value != "take"
        first_strikes += records[0].event in ("strike", "foul")
        for record in records:
            pitches += 1
            actions[record.bat.value] += 1
            kinds[record.pitch.kind] += 1
            zones["zone" if record.pitch.zone else "outside"] += 1
            counts[f"{record.observation.balls}-{record.observation.strikes}:{record.bat.value}"] += 1
    return {"match": asdict(spec), "results": dict(results), "pitches": pitches,
            "action_counts": dict(actions), "pitch_type_counts": dict(kinds),
            "location_counts": dict(zones), "count_action_counts": dict(counts),
            "action_rates": {k: v/pitches for k,v in actions.items()},
            "pitch_type_rates": {k: v/pitches for k,v in kinds.items()},
            "first_pitch_swing_rate": first_swings/spec.plate_appearances,
            "first_pitch_strike_rate": first_strikes/spec.plate_appearances}
