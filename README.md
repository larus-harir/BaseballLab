# BaseballLab · 야구 연구실

| 화면 | 하는 일 |
|---|---|
| **선수 가상 대결** `/eramatch` | MLB·KBO·NPB의 선수와 시즌을 선택해 예상 결과와 가상 타석을 비교합니다. |
| **AI 전략 연구** `/match` | 공격·투구 AI가 경기 승패로 배우고, 같은 상황에서 선택이 어떻게 바뀌었는지 봅니다. |
| **KBO 감독 모드** `/manager` | 10팀 중 한 팀의 자리에 내 구단을 넣고, 선수 선발부터 정규시즌 144경기를 운영합니다. |

## 실행

Python 3.11 이상에서 저장소 폴더를 열고 실행하세요. 서버를 켜 둔 상태라면 먼저 `Ctrl+C`로 종료하세요.

```powershell
git pull origin main
python -m pip install -e ".[learning]"
python scripts/quickstart.py --open
```

기본 기능은 앱에 포함된 집계를 사용합니다. 브라우저는 `http://127.0.0.1:8765`에서 열리고, 가상 대결과 학습 결과는 `outputs/workbench/`에 저장됩니다. 폴더를 새로 받아야 한다면 `git clone https://github.com/larus-harir/BaseballLab.git`을 사용하세요. 로컬 실행 기록은 기존 PC의 보관본에서 복구할 수 있습니다.

## KBO 감독 모드

홈에서 **구단 만들기**를 누릅니다. 후보들의 S~D 등급을 보고 직접 선발하거나 **남은 선수 빠르게 선발**을 누릅니다. 라인업에서는 두 선수를 눌러 순서를 바꾸고, 선수 이름 옆에서 등급과 주요 기록을 비교합니다. 집중 훈련은 선수 상세에서 최대 세 명에게 배정할 수 있습니다. 30경기(마지막 구간 24경기)마다 결과 팝업을 보고 다음 구간 전에 선수 한 자리를 교체할 수 있습니다. **새 시즌**은 같은 구단의 새 선발을 바로 열며, 이전 시즌은 기존 주소나 브라우저 뒤로 가기로 다시 열 수 있습니다.

정규시즌 상위 5팀은 와일드카드, 준플레이오프, 플레이오프, 한국시리즈를 치릅니다. 와일드카드는 4위 홈에서 최대 2경기이며 4위는 1승 또는 무승부, 5위는 2승으로 진출합니다. 준플레이오프·플레이오프는 5전 3선승, 한국시리즈는 7전 4선승과 2–3–2 홈 배정입니다. 내 구단 경기는 한 경기씩 진행하고 다른 구단끼리 치르는 경기는 자동으로 마칩니다. 시드 동률 판정에는 게임 기준을 적용합니다. [KBO 포스트시즌 경기 방식](https://www.chosun.com/english/sports-en/2025/09/28/6W6B53MR6FGPROYIFXNP7UXKPM/)

**시즌 성적표**에서는 정규시즌·포스트시즌 성적, 우승팀, 교체 선수를 포함한 시즌 기록을 확인합니다. 새 시즌에서는 KBO의 주자·아웃별 득점 기대값을 기준으로 게임 MVP를, 포지션별 순 안타 저지로 수비 골드글러브를 뽑습니다. 주력의 기준은 2026 KBO 타석 대비 도루 시도이며, 단타 때 1루 주자의 3루 진루에만 반영합니다. 포지션과 수비 등급은 게임에서 배정하며, 수비는 단타와 인플레이 아웃에만 영향을 줍니다. 기존 저장은 당시 경기 규칙으로 이어서 진행됩니다. 시즌 파일은 `outputs/manager/`에 저장합니다. [Football Manager](https://www.footballmanager.com/) · [ManagerLeague](https://www.managerleague.com/)

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
