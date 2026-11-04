"""A reusable, validated tournament runner. It has no experiment-specific IDs."""

from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from baseball_lab.agents.registry import PolicyRegistry, baseline_registry
from baseball_lab.core.engine import Engine
from baseball_lab.evaluation.matches import MatchSpec, evaluate
from baseball_lab.outcome.synthetic import SyntheticOutcome
from baseball_lab.tracking.events import EventWriter
from baseball_lab.tracking.results import save
from .config import ExperimentConfig


def run_experiment(
    config: ExperimentConfig, output: Path, *, experiment_id: str,
    registry: PolicyRegistry | None = None, outcome=None, trace: bool = True, test_only: bool = False,
) -> dict:
    if not test_only:
        raise ValueError("합성 기준선 실행은 단위 테스트 전용입니다. 실제 기록 모델을 준비하세요.")
    registry = registry if registry is not None else baseline_registry()
    engine = Engine(config.rules, config.profile,
                    outcome if outcome is not None else SyntheticOutcome(), config.attributes)
    # Validate the entire tournament before creating output files or playing any PA.
    for role, names in (("batter", config.batters), ("pitcher", config.pitchers)):
        for name in names:
            registry.resolve(role, name)
    if not experiment_id:
        raise ValueError("experiment_id is required")
    # Stage a complete run before replacing known artifacts. A failed model must not
    # leave a new partial pitch trace beside an old, apparently successful manifest.
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".baseball-run-", dir=output.parent) as temporary:
        staging = Path(temporary)
        with EventWriter(staging / "pitches.csv") if trace else nullcontext() as sink:
            matches = [
                evaluate(engine, MatchSpec(batter, pitcher, seed, config.plate_appearances),
                         registry=registry, event_sink=sink)
                for seed in config.seeds for batter in config.batters for pitcher in config.pitchers
            ]
        payload = save(staging, config.profile, config.rules, matches, config.to_dict(),
                       experiment_id=experiment_id, attributes=config.attributes)
        output.mkdir(parents=True, exist_ok=True)
        for filename in ("pitches.csv", "matchups.csv", "summary.md"):
            if (staging / filename).exists():
                (staging / filename).replace(output / filename)
        if not trace:
            (output / "pitches.csv").unlink(missing_ok=True)
        # Manifest is replaced last. Filesystem-level multi-file transactions are not implied.
        (staging / "results.json").replace(output / "results.json")
    return payload
