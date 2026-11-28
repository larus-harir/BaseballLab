# BaseballLab · 야구 연구실

| 화면 | 하는 일 |
|---|---|
| **선수 가상 대결** `/eramatch` | MLB·KBO·NPB의 선수와 시즌을 선택해 예상 결과와 가상 타석을 비교합니다. |
| **AI 전략 연구** `/match` | 공격·투구 AI가 경기 승패로 배우고, 같은 상황에서 선택이 어떻게 바뀌었는지 봅니다. |

## 실행

Python 3.11 이상에서 저장소 폴더를 열고 실행하세요. 서버를 켜 둔 상태라면 먼저 `Ctrl+C`로 종료하세요.

```powershell
git pull origin main
python -m pip install -e ".[learning]"
python scripts/quickstart.py --open
```

기본 기능은 앱에 포함된 집계를 사용합니다. 브라우저는 `http://127.0.0.1:8765`에서 열리고, 가상 대결과 학습 결과는 `outputs/workbench/`에 저장됩니다. 폴더를 새로 받아야 한다면 `git clone https://github.com/larus-harir/BaseballLab.git`을 사용하세요. 로컬 실행 기록은 기존 PC의 보관본에서 복구할 수 있습니다.

## 결과 확인

- **선수 대결**에서 타자·투수 시즌을 각각 고릅니다. 다른 리그를 맞붙이려면 **다른 리그·시즌 비교**에서 기준 환경도 선택합니다. **다시 대결**은 새 타석을 뽑고, **같은 대결 재현**은 당시 기록과 설정이 일치할 때 같은 순서를 복원합니다. 확률과 가상 결과 개수는 결과 화면에서 나란히 봅니다.
- **AI 학습**은 MLB 2010~2026, KBO 2016~2026, NPB 2019~2026의 총 36개 경기 환경을 기본으로 사용합니다. 앞선 KBO·NPB 시즌의 집계는 참고 기록입니다. 공격·투구 정책 각 하나가 양쪽 역할의 경험을 학습하며, 독립 실행 세 번의 결과를 비교합니다. **학습 결과 보기**와 **한눈에 보기**에서 전체 공격·투구 기록과 전후 평균을 비교합니다. 카운트와 코스는 상세 탭에 있습니다.
- **결과에서 알 수 있는 범위**는 가상 타석의 분포와 시뮬레이션 안에서 바뀐 선택입니다. 실제 리그 간 절대 실력과 승률 향상은 각각 별도 평가가 필요합니다. 자료 범위와 계산 조건은 각 결과의 상세 화면에서 확인할 수 있습니다.

## 다음 게임에서 재사용하기

선수 육성과 감독 시뮬을 위한 코드 진입점, 입력 조건, 저장 형식은 [공통 기반과 재사용 안내](docs/platform/README.md)에 정리했습니다. [학습 정책](docs/match/README.md), [데이터 출처와 사용 조건](docs/league-data-contract.md), [이전 연구](docs/r1-research.md)는 별도로 확인할 수 있습니다.

## 검증

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/audit_repository.py
```

Playwright와 Chromium을 준비한 개발 환경에서는 `scripts/check_product_revision_browser.py`로 대결·저장·모바일 흐름을, `scripts/check_corpus_learning_browser.py`로 새 학습과 보고서를 확인합니다. 저장된 학습 보고서만 확인하려면 두 번째 스크립트에 `--reuse-latest`를 붙입니다. 자료와 결과 원본은 웹의 **자료 관리**에서 확인합니다.

The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.
