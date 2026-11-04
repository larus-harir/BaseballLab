"""Validated settings consumed before a tournament starts or writes output."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from baseball_lab.core.contracts import LeagueProfile, PlayerAttributes, RuleSet, positive_integer


def unique_strings(values, name):
    if (not isinstance(values, list) or not values
            or any(not isinstance(v, str) or not v for v in values)
            or len(set(values)) != len(values)):
        raise ValueError(f"{name} must contain unique, nonempty policy IDs")
    return tuple(values)


@dataclass(frozen=True)
class ExperimentConfig:
    seeds: tuple[int, ...]
    plate_appearances: int
    batters: tuple[str, ...]
    pitchers: tuple[str, ...]
    profile: LeagueProfile
    rules: RuleSet
    attributes: PlayerAttributes

    @classmethod
    def from_dict(cls, raw: dict):
        if not isinstance(raw, dict):
            raise ValueError("Experiment config must be a JSON object")
        unknown = set(raw) - {"seed", "seeds", "plate_appearances", "batters", "pitchers", "profile", "rules", "attributes"}
        if unknown:
            raise ValueError(f"Unknown config fields: {sorted(unknown)}")
        if "seed" in raw and "seeds" in raw:
            raise ValueError("Use either seed or seeds, not both")
        seeds = raw.get("seeds", [raw.get("seed", 20261104)])
        if (not isinstance(seeds, list) or not seeds or any(type(s) is not int for s in seeds)
                or len(set(seeds)) != len(seeds)):
            raise ValueError("seeds must be a nonempty list of unique integers")
        try:
            positive_integer(raw["plate_appearances"], "plate_appearances")
            return cls(
                tuple(seeds), raw["plate_appearances"],
                unique_strings(raw["batters"], "batters"), unique_strings(raw["pitchers"], "pitchers"),
                LeagueProfile(**raw.get("profile", {})), RuleSet(**raw.get("rules", {})),
                PlayerAttributes(**raw.get("attributes", {})),
            )
        except (TypeError, KeyError) as exc:
            raise ValueError(f"Invalid experiment config: {exc}") from exc

    @classmethod
    def load(cls, path: Path):
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        result = asdict(self)
        for name in ("seeds", "batters", "pitchers"):
            result[name] = list(result[name])
        return result
