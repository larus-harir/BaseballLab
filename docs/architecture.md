# 공통 플랫폼과 자식 실험

## 실행 흐름

```text
E01 설정 JSON → ExperimentConfig → run_experiment
  → RuleSet + LeagueProfile + OutcomeModel + PlayerAttributes → Engine
  → PolicyRegistry → 호환성 검사 → MatchSpec별 evaluate
  → PitchEvent 스트림 + 집계 → JSON / CSV / Markdown
```

E01의 자체 실행 입구는 공통 CLI에 연결됩니다. 실험 레지스트리는 자식의 ID·이름·설정 위치를 보관합니다. 새 자식은 공통 `run_experiment`에 자신의 ID와 설정을 주입합니다. 평가기와 기록기에 E01 이름을 고정하지 않습니다.

## 경계와 계약

- `core`: 카운트와 사건을 타석 종료로 바꾸는 규칙. 확률·리그별 분기는 없습니다. 볼넷/삼진/인플레이 종료, 2스트라이크 이후 파울 유지를 처리합니다.
- `OutcomeModel.sample(..., context=OutcomeContext(...))`: 공개 상태와 합성 선수 능력을 받아 사건을 생성합니다. 다른 보정 모델을 주입할 수 있고, 프로파일의 calibration_id가 다르면 시작 전에 오류를 냅니다.
- `Policy.act(observation, legal_actions, rng)`: 현재 카운트만 관찰합니다. 실제 구종·목표 코스·결과는 정책 호출이 끝난 뒤 모델에 전달하며, 정책 관측에 넣지 않습니다.
- `PolicyRegistry`: 역할·정책 ID를 실제 구현과 메타데이터에 연결합니다. 평가 전에 양쪽 스키마를 검사하고 불일치·미등록 정책을 거부합니다. 훈련 리그가 다르다는 이유로 거부하지 않으므로 교차 리그 평가를 지원합니다.
- `PlayerAttributes`: 현재 contact/power/control은 [0,1]의 합성 계수입니다. 기본값은 양쪽 환경에서 같습니다. 실측 선수 등급이나 물리 구속이 아니며 프로파일 이름만 바꿔 실제 리그 능력을 구현한 것으로 간주하지 않습니다.
- `PitchEvent`: 출처·버전·리그·seed·매치 ID·타석/투구 번호·사전 카운트·행동·사건·종료 결과. 로그는 사후 연구용이며 정책 관측으로 그대로 넣지 않습니다.
- `tracking`: 실험 ID·설정·능력·정책 버전·Python·Git revision/dirty·소스 SHA256·RNG 버전을 기록합니다. Git 명령이 없는 로컬 환경에서도 실행됩니다.

현재 스키마는 `count-v1`, `discrete-pitch-swing-v1`, `pitch-event-v1`, 출력 스키마는 `experiment-result-v2`입니다. 미래 관측·행동을 확장할 때 버전과 어댑터를 함께 정의합니다. PolicyMetadata는 policy_version, observation/action_schema, training_league, ruleset, calibration, source_data_version, algorithm, seed, commit을 보존합니다. M1은 체크포인트를 로딩하지 않고 동일 계약의 고정 기준선을 등록합니다.

## 새 실험 추가

1. `experiments/<ID>/`에 가설·데이터·평가 조건을 설명하는 README와 JSON 설정을 둡니다.
2. `ExperimentConfig.load(path)`로 설정을 읽고 `run_experiment(config, output, experiment_id="<ID>")`를 호출합니다. 부모 CLI에도 노출하려면 실험 레지스트리에 ID·이름·설정 위치를 추가합니다.
3. 새로운 정책은 `PolicyEntry`로 등록하고 `registry=`를 주입합니다. 새로운 데이터 보정은 OutcomeModel을 구현해 `outcome=`로 주입합니다. 핵심 엔진·평가·기록은 복사하지 않습니다.
4. `tests/test_platform.py`의 `test_new_policy_and_league_use_same_engine_and_recorder`처럼 기존 엔진에서 새 정책·프로파일·실험 ID를 실제로 실행하는 테스트를 추가합니다.

```python
from pathlib import Path
from baseball_lab.experiments import ExperimentConfig, run_experiment

config = ExperimentConfig.load(Path("experiments/E01_batter_pitcher_evolution/configs/m1_baseline.json"))
run_experiment(config, Path("outputs/my_experiment"), experiment_id="MY_EXPERIMENT")
```

## 재현성과 파일 처리

`per-pa-stream-v2`는 seed·타석 번호·역할로 별도 RNG를 만듭니다. 상대 정책의 난수 호출 수나 이전 타석 길이가 다음 타석 시작 스트림을 바꾸지 않습니다. 정책별 동일 seed 비교를 돕지만, 분포가 다른 두 정책의 투구별 결과가 동일하다는 뜻은 아닙니다. 구버전 rng-v1과 결과가 다르며 메타데이터로 구별합니다.

전체 설정·정책·프로파일을 먼저 검증합니다. 실행 결과를 임시 디렉터리에서 완성한 다음 지정 경로의 알려진 파일을 갱신합니다. 시뮬레이션 실패 시 기존 결과를 보존하며, 여러 파일 교체 도중 시스템 장애까지 원자적으로 복구하는 DB 트랜잭션은 구현하지 않았습니다.

## 경기·학습으로 연결

타석은 매번 초기화됩니다. 경기 상태(주자/득점/이닝/선후공)는 다음 단계에서 이 타석 엔진의 상위에 연결하고, 데이터 보정 모델과 정책 평가를 재사용합니다. 최종 학습 보상은 경기 승패이며, BB/K/장타/스윙률은 관찰 지표입니다. 단계별 검증 결과를 바탕으로 데이터 보정 → 전체 경기 → 경쟁 학습으로 개발을 이어갑니다.
