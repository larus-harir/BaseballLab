# Baseball AI Lab

야구 AI 연구를 계속 추가할 수 있는 부모 플랫폼입니다. 핵심 질문은 **승리만 추구하는 AI가 어떤 전략을 스스로 발전시키는가, 그리고 인간 야구의 역사·현대 전략과 어떻게 다른가**입니다.

현재는 M0 + E01 M1: 합성 확률을 사용하는 타석 시뮬레이션과 비교용 고정 정책만 구현했습니다. 학습·진화·9이닝 경기·승률·실제 MLB/KBO 검증은 아직 없습니다. 타율, 삼진, 장타 등 관찰 지표를 보상으로 사용하지 않습니다.

## 실행

Python 3.11 이상. 시뮬레이션은 외부 패키지 없이 실행됩니다.

```bash
python scripts/quickstart.py
```

랜덤/적극/인내 타자 × 랜덤/스트라이크 우선/혼합 투수 9개 조합, 각 1,000타석, seed `20261104`. 결과는 `outputs/E01/results.json`, `matchups.csv`에 저장됩니다. 동일 경로 재실행 시 결과 파일을 갱신하므로 보존하려면 `--output outputs/E01/run2`를 사용하세요.

```bash
python -m venv .venv
# Linux/macOS
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
# Windows에서는 .venv/Scripts/python.exe 사용
```

필수 검증은 규칙·확률·재현성·호환성 테스트와 quickstart 전체 대결입니다. 외부 데이터/API, GPU, DB, 웹 서버는 필요하지 않습니다.

## 구조

| 경로 | 역할 |
|---|---|
| `src/baseball_lab/core` | 상태 전이, 합법 행동, 공개 관측, RuleSet/LeagueProfile/Policy 계약 |
| `outcome` | 교체 가능한 결과 확률 모델; 현재 synthetic-v1 |
| `agents` | 고정 비교 정책, 미래 체크포인트 메타데이터·스키마 검증 |
| `data` | 출처 계약; 실제 어댑터는 M2 |
| `evaluation` | MatchSpec과 공통 대결·행동 집계 |
| `tracking` | 설정·환경·코드 버전과 JSON/CSV 결과 |
| `training` | M4 학습 코드의 위치만 예약 |
| `experiments/E01_batter_pitcher_evolution` | E01 설정·실행 입구·가설 |
| `experiments/E02_mlb_vs_kbo` | 후속 연구 설계만 |

[아키텍처](docs/architecture.md), [연구 원칙](docs/research-principles.md), [데이터 계획](docs/data-sources.md), [검증 기록](docs/m1-validation.md), [다음 M2 작업](docs/next-m2.md)을 참고하세요.

새 실험은 `experiments/<ID>/README.md`, 설정, 실행 스크립트를 추가하고 공통 `Engine`, `evaluate`, `save`를 사용합니다. 규칙/확률 구현을 복사하지 않습니다.
