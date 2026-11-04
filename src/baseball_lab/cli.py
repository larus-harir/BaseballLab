"""Command line interface for the parent research platform."""

import argparse
from pathlib import Path

from baseball_lab.labels import korean
from baseball_lab.experiments.config import ExperimentConfig
from baseball_lab.experiments.registry import EXPERIMENTS, REPOSITORY_ROOT
from baseball_lab.experiments.runner import run_experiment


def main():
    parser = argparse.ArgumentParser(description="Baseball AI Lab — 야구 AI 연구 실험 실행")
    parser.add_argument("--mode", choices=("train", "baseline", "replay"), default="train", help="train: 실제 학습 / baseline: 고정 전략 비교 / replay: 저장 정책 평가")
    parser.add_argument("--games", type=int, default=600, help="학습 경기 수")
    parser.add_argument("--innings", type=int, default=3, help="경기 이닝 수 (9이닝도 가능)")
    parser.add_argument("--evaluate-every", type=int, default=200)
    parser.add_argument("--evaluation-pairs", type=int, default=12, help="상대별 선후공 교환 평가 쌍 수")
    parser.add_argument("--checkpoint", type=Path, help="재평가할 신경망 체크포인트")
    parser.add_argument("--open", action="store_true", help="완료 후 한국어 HTML 보고서 열기")
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
            print(f"{item.experiment_id}: {korean(item.experiment_id)}")
        return
    definition = EXPERIMENTS[args.experiment]
    if args.checkpoint is not None and args.mode != "replay":
        parser.error("저장 정책은 --mode replay와 함께 실행하세요. 이어 학습 옵션이 아닙니다.")
    if args.mode != "baseline":
        if args.config or args.seeds is not None or args.plate_appearances is not None or args.no_trace:
            parser.error("타석 기준선 옵션은 --mode baseline과 함께 사용하세요.")
        try:
            from baseball_lab.training.self_play import TrainingConfig, train
            if args.mode == "replay":
                if args.checkpoint is None:
                    parser.error("--mode replay에는 --checkpoint가 필요합니다.")
                from baseball_lab.training.replay import replay_checkpoint
                output = args.output or REPOSITORY_ROOT / "outputs/E01/replay"
                replay_checkpoint(args.checkpoint, output, pairs=args.evaluation_pairs)
            else:
                from datetime import datetime
                output = args.output or REPOSITORY_ROOT / "outputs/E01" / ("학습_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
                config = TrainingConfig(games=args.games, innings=args.innings,
                                        seed=args.seed if args.seed is not None else 20261104,
                                        evaluate_every=args.evaluate_every, evaluation_pairs=args.evaluation_pairs)
                train(config, output, experiment_id=args.experiment)
            if args.open:
                import webbrowser
                webbrowser.open((output / "report.html").resolve().as_uri())
        except ImportError as exc:
            parser.exit(2, f"학습 의존성을 설치하세요: python -m pip install -e \".[learning]\"\n({exc})\n")
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            parser.exit(2, f"학습 실행 오류: {exc}\n")
        return
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
    print(f"{definition.experiment_id}: {korean(definition.experiment_id)}")
    print(f"환경: {korean(config.profile.league_id)} / {korean(config.profile.calibration_id)}")
    print("고정 기준선의 타석 시뮬레이션입니다. 학습 여부: 없음")
    print(f"{'타자':12} {'투수':14} {'타석':>6} {'볼넷비율':>8} {'삼진비율':>8} {'초구스윙':>9}")
    for item in payload["summary"]:
        print(f"{korean(item['batter']):12} {korean(item['pitcher']):14} {item['plate_appearances']:6} "
              f"{item['walk_rate']:8.1%} {item['strikeout_rate']:8.1%} {item['first_pitch_swing_rate']:9.1%}")
    print(f"완료: {len(payload['matches'])}개 대결 / 총 {sum(m['match']['plate_appearances'] for m in payload['matches']):,}타석")
    print(f"결과 폴더: {output.resolve()}")
    print("summary.md: 전략 요약·매치업 행렬 / results.json: 상세 결과 / matchups.csv: 대결표")
    if not args.no_trace:
        print("pitches.csv: 투구별 행동·카운트·사건 기록")
