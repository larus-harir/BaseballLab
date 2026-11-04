"""Versioned simulation event records, separate from the policy observation schema."""

from dataclasses import asdict, dataclass

from baseball_lab.core.contracts import LeagueProfile
from baseball_lab.core.engine import PitchRecord

EVENT_SCHEMA = "pitch-event-v1"


@dataclass(frozen=True)
class PitchEvent:
    schema_version: str
    league: str
    season: str
    source: str
    source_version: str
    match_id: str
    seed: int
    batter_policy: str
    pitcher_policy: str
    plate_appearance: int
    pitch_number: int
    balls: int
    strikes: int
    pitch_type: str
    target_zone: bool
    batter_action: str
    event: str
    result: str

    @classmethod
    def from_record(cls, profile: LeagueProfile, match_id: str, seed: int,
                    batter: str, pitcher: str, pa: int, pitch_number: int,
                    record: PitchRecord, result: str = ""):
        return cls(
            EVENT_SCHEMA, profile.league_id, profile.season, profile.data_provenance,
            profile.source_data_version, match_id, seed, batter, pitcher, pa, pitch_number,
            record.observation.balls, record.observation.strikes, record.pitch.kind,
            record.pitch.zone, record.bat.value, record.event, result,
        )

    def to_dict(self) -> dict:
        return asdict(self)
