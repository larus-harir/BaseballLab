"""Experiment-independent manifests, matchup tables and readable research reports."""

import csv
import hashlib
import json
import platform
import subprocess
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from baseball_lab.core.contracts import ACTION_SCHEMA, OBSERVATION_SCHEMA
from baseball_lab.data.schema import EVENT_SCHEMA


def code_identity(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[3]

    def git(*args):
        try:
            result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else None
        except OSError:
            return None

    digest = hashlib.sha256()
    paths = {root / "pyproject.toml"}
    for directory in ("src", "scripts", "experiments"):
        paths.update(path for path in (root / directory).rglob("*")
                     if path.suffix in (".py", ".json") and path.is_file())
    for path in sorted(paths):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    status = git("status", "--porcelain")
    return {"code_sha256": digest.hexdigest(), "code_revision": git("rev-parse", "HEAD") or "unavailable",
            "working_tree_dirty": bool(status) if status is not None else None}


def summarize(matches: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for match in matches:
        grouped[match["match"]["batter"], match["match"]["pitcher"]].append(match)
    summary = []
    for (batter, pitcher), group in grouped.items():
        total_pa = sum(m["match"]["plate_appearances"] for m in group)
        total_pitches = sum(m["pitches"] for m in group)
        summary.append({
            "batter": batter, "pitcher": pitcher, "seeds": [m["match"]["seed"] for m in group],
            "plate_appearances": total_pa, "pitches": total_pitches,
            "walk_rate": sum(m["results"]["walk"] for m in group)/total_pa,
            "strikeout_rate": sum(m["results"]["strikeout"] for m in group)/total_pa,
            "hit_rate": sum(sum(m["results"][k] for k in ("single", "double", "triple", "home_run")) for m in group)/total_pa,
            "first_pitch_swing_rate": sum(m["first_pitch_swing_rate"]*m["match"]["plate_appearances"] for m in group)/total_pa,
            "seed_walk_rates": [m["metrics"]["walk_rate"]["value"] for m in group],
            "seed_strikeout_rates": [m["metrics"]["strikeout_rate"]["value"] for m in group],
        })
    return summary


def report(payload: dict) -> str:
    lines = [f"# {payload['experiment_id']} 실행 결과", "",
             f"프로파일: `{payload['profile']['league_id']}` / 보정: `{payload['profile']['calibration_id']}`",
             f"데이터 출처: {payload['profile']['data_provenance']}", "",
             "타석 단위의 정책 평가다. 이 실행은 학습을 수행하지 않으며 경기 승패를 측정하지 않는다.", "",
             "## 대결 요약", "",
             "| 타자 | 투수 | seed 수 | 타석 | BB% | K% | 안타/타석 | 초구 스윙% |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for item in payload["summary"]:
        lines.append(f"| {item['batter']} | {item['pitcher']} | {len(item['seeds'])} | {item['plate_appearances']} | "
                     f"{item['walk_rate']:.1%} | {item['strikeout_rate']:.1%} | {item['hit_rate']:.1%} | "
                     f"{item['first_pitch_swing_rate']:.1%} |")
    batters = list(dict.fromkeys(m["batter"] for m in payload["summary"]))
    pitchers = list(dict.fromkeys(m["pitcher"] for m in payload["summary"]))
    lookup = {(m["batter"], m["pitcher"]): m for m in payload["summary"]}
    for metric, label in (("walk_rate", "볼넷 비율"), ("strikeout_rate", "삼진 비율")):
        lines.extend(["", f"## 매치업 행렬: {label}", "",
                      "| 타자 / 투수 | " + " | ".join(pitchers) + " |",
                      "|---|" + "---:|"*len(pitchers)])
        for batter in batters:
            values = [f"{lookup[batter, pitcher][metric]:.1%}" if (batter, pitcher) in lookup else "—" for pitcher in pitchers]
            lines.append("| " + batter + " | " + " | ".join(values) + " |")
    lines.extend(["", "## 지표·재현성", "",
                  "- BB%, K%, 안타/타석의 분모는 타석 수다. 안타/타석은 타율(안타/타수)과 다르다.",
                  "- 초구 스트라이크는 첫 공의 strike/foul 사건이며 인플레이는 포함하지 않는다.",
                  "- whiff_per_swing은 스윙 중 strike 사건 비율이다. 스윙이 없으면 null이다.",
                  "- results.json에 카운트별 행동·구종 비율, 정책 버전, seed별 결과와 Wilson 95% 구간이 있다.",
                  "- Wilson 구간은 각 고정 정책·seed 실행의 이항 표본 요약이다. 모델 편향이나 학습 seed 불확실성을 포함하지 않는다.",
                  "- 정책·확률·코드가 같을 때 재현 가능하다. rng-v2는 타석마다 독립 스트림을 시작한다.",
                  "- 이 지표는 관찰용이며 학습 보상이 아니다. 최종 연구 목표는 경기 승리다.",
                  f"- 코드: `{payload['code_revision']}`, SHA256: `{payload['code_sha256']}`", ""])
    return "\n".join(lines)


def save(
    output: Path, profile, rules, matches: list[dict], config: dict, *,
    experiment_id: str, stage: str = "M1", attributes=None,
) -> dict:
    if not experiment_id or not matches:
        raise ValueError("Experiment identity and nonempty results are required")
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        **code_identity(), "result_schema": "experiment-result-v2",
        "experiment_id": experiment_id, "stage": stage, "trained": False, "training_executed": False,
        "profile": asdict(profile), "rules": asdict(rules), "config": config,
        "attributes": asdict(attributes) if attributes is not None else None,
        "schemas": {"observation": OBSERVATION_SCHEMA, "action": ACTION_SCHEMA, "event": EVENT_SCHEMA},
        "python": platform.python_version(), "rng_version": "per-pa-stream-v2",
        "matches": matches, "summary": summarize(matches),
        "artifacts": ["results.json", "matchups.csv", "summary.md"] + (["pitches.csv"] if (output / "pitches.csv").exists() else []),
    }
    (output / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    with (output / "matchups.csv").open("w", newline="", encoding="utf-8") as file:
        fields = ["batter", "pitcher", "seed", "plate_appearances", "pitches", "walks", "strikeouts",
                  "first_pitch_swing_rate", "first_pitch_strike_rate", "take_rate", "contact_rate", "power_rate",
                  "walk_rate", "strikeout_rate", "hit_rate"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for match in matches:
            writer.writerow({
                **match["match"], "pitches": match["pitches"],
                "walks": match["results"]["walk"], "strikeouts": match["results"]["strikeout"],
                "first_pitch_swing_rate": match["first_pitch_swing_rate"],
                "first_pitch_strike_rate": match["first_pitch_strike_rate"],
                **{f"{key}_rate": value for key, value in match["action_rates"].items()},
                **{key: match["metrics"][key]["value"] for key in ("walk_rate", "strikeout_rate", "hit_rate")},
            })
    (output / "summary.md").write_text(report(payload), encoding="utf-8")
    return payload
