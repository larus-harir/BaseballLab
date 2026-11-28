# 공통 기반과 재사용 안내

| 용도 | 코드 진입점 | 입력과 결과 |
|---|---|---|
| 선수 기록 조회와 타석 대결 | `matchup/service.py`의 `overview`, `analyze` | 선수 ID·시즌·자료 모드·타석 수·재현 번호를 받습니다. `model.probabilities`는 예상 확률, `simulation.events`는 추첨된 타석 순서입니다. |
| 리그·시즌을 섞어서 비교 | `matchup/shared.py`의 `analyze` | 타자·투수 자료와 비교 기준 리그·시즌을 받습니다. 공통 사건 정의를 적용하고 사용 가능한 장타·사구는 따로 계산합니다. |
| 투구와 카운트 진행 | `core/engine.py`의 `transition`, `Engine` | 볼·스트라이크·타석 종료 규칙을 처리합니다. `core/contracts.py`의 `Policy`, `OutcomeModel`로 선택과 결과 모델을 연결합니다. |
| 이닝·주자·점수 진행 | `core/game.py`의 `GameEngine` | 규칙과 결과 모델을 주입하는 단순 경기 엔진입니다. `advance`의 진루는 명시된 단순화이며 새 게임에 필요한 주루 규칙을 검토해야 합니다. |
| 관측 기록 기반 경기와 AI 학습 | `experiments/match/pitch_game/modern_world.py`의 `ModernWorld`, `research.py`의 `play`, `train` | 리그·시즌별 환경에서 합법 행동을 열고 경기 승패로 정책을 갱신합니다. 관측 항목·행동·가중치 버전을 함께 맞춰야 합니다. |

**선수 육성**에서 선수 시즌 기록과 타석 분포를 출발점으로 사용할 수 있습니다. 성장에 따른 능력치 변화와 선수의 성장 곡선은 게임에서 정의해야 합니다. `PA` 또는 `TBF`를 분모로 쓰고 관측되지 않은 사건은 결측으로 관리합니다. `simulation/contracts.py`와 `matchup/event_schema.py`에 프로필 조건과 사건 분류가 있습니다. 타석 사건 `other`에는 아웃과 실책 출루 등이 함께 들어갈 수 있으므로 주자 이동에 바로 넣기 전에 사건을 구분할 모델이 필요합니다.

**감독 시뮬**에서는 투구에서 카운트·아웃·주자·점수를 이어 가는 흐름을 재사용할 수 있습니다. 현재 Match는 대칭적인 실험 명단과 공통 경기 규칙을 쓰므로 로스터 구성, 라인업, 부상, 시즌 일정은 새 게임에서 정의해야 합니다. 구종·코스나 주루 선택은 관측 기록이 지원하는 범위에서 열립니다. 선택 확률의 변화와 고정 상대에 대한 성능 평가는 서로 다른 측정입니다.

| 보관 파일 | 용도 |
|---|---|
| `analysis.json` | 대결의 선수·자료·계산 조건, 확률과 타석 순서. `run_id`는 재현 조건, `execution_id`는 개별 실행을 식별합니다. |
| `research.json`, `world.json`, `checkpoints/` | 학습 기록, 환경 계수와 근거, 정책·행동 순서. 분석과 재현의 원본입니다. |
| `report.html`, `overview.html`, `report-data.json` | 완료 결과를 읽는 화면과 표시용 데이터. 게임과 분석에서는 원본 JSON을 사용하세요. |

웹 진입점은 `/eramatch`, `/match`, `/match/team`입니다. `/baseball`은 MLB 대결의 호환 경로입니다. 기본 대결·통합 학습은 앱에 포함된 집계를 사용합니다. 개별 출처의 검증 범위와 사용 조건은 [데이터 규칙](../league-data-contract.md), 학습 실행과 결과는 [Match 안내](../match/README.md)에서 확인합니다.
