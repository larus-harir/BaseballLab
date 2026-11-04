import csv
import hashlib
import json
import platform
import subprocess
from dataclasses import asdict
from pathlib import Path
from baseball_lab.core.contracts import ACTION_SCHEMA, OBSERVATION_SCHEMA

def save(output: Path, profile, rules, matches: list[dict], config: dict):
    output.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True)
    digest = hashlib.sha256()
    for path in sorted([*repo.glob("src/**/*.py"), *repo.glob("experiments/**/*.py"), *repo.glob("experiments/**/*.json")]):
        digest.update(str(path.relative_to(repo)).encode())
        digest.update(path.read_bytes())
    payload = {"code_sha256": digest.hexdigest(),"experiment_id": "E01", "stage": "M1", "trained": False,
               "profile": asdict(profile), "rules": asdict(rules), "config": config,
               "schemas": {"observation": OBSERVATION_SCHEMA, "action": ACTION_SCHEMA},
               "python": platform.python_version(), "code_revision": revision.stdout.strip() if revision.returncode == 0 else "unborn",
               "working_tree_dirty": bool(status.stdout), "matches": matches}
    (output/"results.json").write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n")
    with (output/"matchups.csv").open("w", newline="") as f:
        fields = ["batter", "pitcher", "seed", "plate_appearances", "pitches", "walks", "strikeouts", "first_pitch_swing_rate"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for m in matches:
            writer.writerow({**m["match"], "pitches": m["pitches"], "walks": m["results"].get("walk", 0),
                             "strikeouts": m["results"].get("strikeout", 0), "first_pitch_swing_rate": m["first_pitch_swing_rate"]})
