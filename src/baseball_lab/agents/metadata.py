from dataclasses import dataclass
from baseball_lab.core.contracts import ACTION_SCHEMA, OBSERVATION_SCHEMA

@dataclass(frozen=True)
class PolicyMetadata:
    policy_version: str
    observation_schema: str
    action_schema: str
    training_league: str
    ruleset: str
    calibration: str
    source_data_version: str
    algorithm: str
    seed: int
    commit: str

    def validate_compatibility(self):
        if (self.observation_schema, self.action_schema) != (OBSERVATION_SCHEMA, ACTION_SCHEMA):
            raise ValueError("Incompatible policy schema; explicit adapter required")
