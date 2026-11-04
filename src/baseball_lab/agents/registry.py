"""Explicit policy registration; future learned policies use the same evaluator."""

from dataclasses import dataclass
from typing import Literal

from baseball_lab.core.contracts import ACTION_SCHEMA, OBSERVATION_SCHEMA, Policy
from .baselines import BATTERS, PITCHERS, Batter, Pitcher
from .metadata import PolicyMetadata


@dataclass(frozen=True)
class PolicyEntry:
    policy_id: str
    role: Literal["batter", "pitcher"]
    policy: Policy
    metadata: PolicyMetadata


class PolicyRegistry:
    def __init__(self):
        self._entries: dict[tuple[str, str], PolicyEntry] = {}

    def register(self, entry: PolicyEntry) -> None:
        if entry.role not in ("batter", "pitcher") or not entry.policy_id:
            raise ValueError("Policy role and identity are required")
        key = (entry.role, entry.policy_id)
        if key in self._entries:
            raise ValueError(f"Duplicate policy: {key}")
        self._entries[key] = entry

    def resolve(self, role: str, policy_id: str) -> PolicyEntry:
        try:
            entry = self._entries[role, policy_id]
        except KeyError as exc:
            raise ValueError(f"Unknown {role} policy: {policy_id}") from exc
        entry.metadata.validate_compatibility()
        return entry


def baseline_registry() -> PolicyRegistry:
    registry = PolicyRegistry()
    for role, names, factory in (("batter", BATTERS, Batter), ("pitcher", PITCHERS, Pitcher)):
        for name in names:
            registry.register(PolicyEntry(name, role, factory(name), PolicyMetadata(
                policy_version="baseline-v1", observation_schema=OBSERVATION_SCHEMA,
                action_schema=ACTION_SCHEMA, training_league="not_trained",
                ruleset="count-based", calibration="independent",
                source_data_version="none", algorithm="fixed_baseline", seed=0,
                commit="source_in_run_manifest",
            )))
    return registry
