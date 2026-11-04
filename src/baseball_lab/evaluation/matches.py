"""Common evaluation: registered policies, independent seeds, optional event sink."""

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from random import Random
from typing import Callable

from baseball_lab.agents.registry import PolicyRegistry, baseline_registry
from baseball_lab.core.contracts import BatAction, PITCH_ACTIONS, positive_integer
from baseball_lab.core.engine import Engine, TERMINAL_RESULTS
from baseball_lab.data.schema import PitchEvent
from .metrics import rates, wilson_interval


@dataclass(frozen=True)
class MatchSpec:
    batter: str
    pitcher: str
    seed: int
    plate_appearances: int

    def __post_init__(self):
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        positive_integer(self.plate_appearances, "plate_appearances")
        if not self.batter or not self.pitcher:
            raise ValueError("Both policy IDs are required")

    @property
    def match_id(self) -> str:
        value = f"{self.batter}\0{self.pitcher}\0{self.seed}"
        return hashlib.sha256(value.encode()).hexdigest()[:16]


def random_stream(seed: int, pa: int, role: str) -> Random:
    # Reinitializing per PA prevents differing PA lengths from shifting later starts.
    return Random(f"baseball-lab-rng-v2:{seed}:{pa}:{role}")


def evaluate(
    engine: Engine, spec: MatchSpec, *, registry: PolicyRegistry | None = None,
    event_sink: Callable[[PitchEvent], None] | None = None,
) -> dict:
    registry = registry if registry is not None else baseline_registry()
    batter = registry.resolve("batter", spec.batter)
    pitcher = registry.resolve("pitcher", spec.pitcher)
    results = Counter({key: 0 for key in TERMINAL_RESULTS})
    actions = Counter({action.value: 0 for action in BatAction})
    kinds = Counter({kind: 0 for kind in dict.fromkeys(p.kind for p in PITCH_ACTIONS)})
    zones = Counter({"zone": 0, "outside": 0})
    counts, by_count = Counter(), {}
    first_swings = first_strikes = pitches = whiffs = swings = 0
    for pa in range(1, spec.plate_appearances + 1):
        final, records = engine.play(
            batter.policy, pitcher.policy,
            *(random_stream(spec.seed, pa, role) for role in ("batter", "pitcher", "outcome")),
        )
        results[final.result] += 1
        first_swings += records[0].bat != BatAction.TAKE
        first_strikes += records[0].event in ("strike", "foul")
        for index, record in enumerate(records, start=1):
            pitches += 1
            swinging = record.bat != BatAction.TAKE
            swings += swinging
            whiffs += swinging and record.event == "strike"
            actions[record.bat.value] += 1
            kinds[record.pitch.kind] += 1
            zones["zone" if record.pitch.zone else "outside"] += 1
            count = f"{record.observation.balls}-{record.observation.strikes}"
            counts[f"{count}:{record.bat.value}"] += 1
            group = by_count.setdefault(count, {"pitches": 0, "batter_actions": Counter(),
                                              "pitch_types": Counter(), "target_zones": Counter()})
            group["pitches"] += 1
            group["batter_actions"][record.bat.value] += 1
            group["pitch_types"][record.pitch.kind] += 1
            group["target_zones"]["zone" if record.pitch.zone else "outside"] += 1
            if event_sink is not None:
                event_sink(PitchEvent.from_record(
                    engine.profile, spec.match_id, spec.seed, spec.batter, spec.pitcher,
                    pa, index, record, final.result if index == len(records) else "",
                ))
    hit_count = sum(results[key] for key in ("single", "double", "triple", "home_run"))
    metrics = {}
    for name, value in (("walk_rate", results["walk"]), ("strikeout_rate", results["strikeout"]), ("hit_rate", hit_count)):
        metrics[name] = {"value": value/spec.plate_appearances,
                         "ci95_wilson": wilson_interval(value, spec.plate_appearances)}
    metrics["whiff_per_swing"] = whiffs/swings if swings else None
    for group in by_count.values():
        for name in ("batter_actions", "pitch_types", "target_zones"):
            group[name] = dict(group[name])
        group["batter_action_rates"] = rates(group["batter_actions"], tuple(actions), group["pitches"])
        group["pitch_type_rates"] = rates(group["pitch_types"], tuple(kinds), group["pitches"])
    return {
        "match": asdict(spec), "match_id": spec.match_id,
        "policies": {"batter": asdict(batter.metadata), "pitcher": asdict(pitcher.metadata)},
        "results": dict(results), "pitches": pitches,
        "action_counts": dict(actions), "pitch_type_counts": dict(kinds),
        "location_counts": dict(zones), "count_action_counts": dict(counts),
        "by_count": by_count, "metrics": metrics,
        "action_rates": rates(actions, tuple(actions), pitches),
        "pitch_type_rates": rates(kinds, tuple(kinds), pitches),
        "location_rates": rates(zones, tuple(zones), pitches),
        "first_pitch_swing_rate": first_swings/spec.plate_appearances,
        "first_pitch_strike_rate": first_strikes/spec.plate_appearances,
    }
