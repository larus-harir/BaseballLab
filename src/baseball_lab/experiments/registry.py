"""Small static experiment registry; each child owns its setup and description."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentDefinition:
    experiment_id: str
    name: str
    config_path: Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS = {
    "E01": ExperimentDefinition(
        "E01", "Batter vs Pitcher Evolution",
        REPOSITORY_ROOT / "experiments/E01_batter_pitcher_evolution/configs/m1_baseline.json",
    ),
}
