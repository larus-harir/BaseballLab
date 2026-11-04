"""Command line interface for the parent research platform."""

import argparse
from pathlib import Path

from baseball_lab.experiments.config import ExperimentConfig
from baseball_lab.experiments.registry import EXPERIMENTS, REPOSITORY_ROOT
from baseball_lab.experiments.runner import run_experiment


def main():
    parser = argparse.ArgumentParser(description="Baseball AI Lab — 야구 AI 연구 실험 실행")
    parser.add_argument("--experiment", choices=EXPERIMENTS, default="E01")
    parser.add_argument("--list", action="store_true", help="실행 가능한 실험 목록")
    parser.add_argument("--config", type=Path, help="실험 JSON 설정")
    parser.add_argument("--output", type=Path, help="결과 저장 경로")
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seed", type=int)
    seed_group.add_argument("--seeds", type=int, nargs="+", help="반복 평가 seed 목록")
    parser.add_argument("--plate-appearances", type=int, help="각 조합·seed별 타석 수")
    parser.add_argument("--no-trace", action="store_true", help="투구별 CSV 없이 집계만 저장")
    args = parser.parse_args()
    if args.list:
        for item in EXPERIMENTS.values():
            print(f"{item.experiment_id}: {item.name}")
        return
    definition = EXPERIMENTS[args.experiment]
    try:
        config = ExperimentConfig.load(args.config or definition.config_path).to_dict()
        if args.seed is not None:
            config["seeds"] = [args.seed]
        elif args.seeds is not None:
            config["seeds"] = args.seeds
        if args.plate_appearances is not None:
            config["plate_appearances"] = args.plate_appearances
        config = ExperimentConfig.from_dict(config)
        output = args.output or REPOSITORY_ROOT / "outputs" / args.experiment
        payload = run_experiment(config, output, experiment_id=args.experiment, trace=not args.no_trace)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        parser.exit(2, f"실행 오류: {exc}\n")
    print(f"{definition.experiment_id}: {definition.name}")
    print(f"환경: {config.profile.league_id} / {config.profile.calibration_id}")
    print("고정 기준선의 타석 시뮬레이션입니다. 학습 여부: 없음")
    print(f"{'타자':12} {'투수':14} {'타석':>6} {'BB%':>8} {'K%':>8} {'초구스윙':>9}")
    for item in payload["summary"]:
        print(f"{item['batter']:12} {item['pitcher']:14} {item['plate_appearances']:6} "
              f"{item['walk_rate']:8.1%} {item['strikeout_rate']:8.1%} {item['first_pitch_swing_rate']:9.1%}")
    print(f"완료: {len(payload['matches'])}개 대결 / 총 {sum(m['match']['plate_appearances'] for m in payload['matches']):,}타석")
    print(f"결과 폴더: {output.resolve()}")
    print("summary.md: 전략 요약·매치업 행렬 / results.json: 상세 결과 / matchups.csv: 대결표")
    if not args.no_trace:
        print("pitches.csv: 투구별 행동·카운트·사건 기록")
