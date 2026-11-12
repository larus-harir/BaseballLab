# BaseballLab · 야구 연구실

실제 기록으로 선수를 맞붙이고, AI가 전략을 바꾸는 과정을 살펴보는 서비스입니다.

| 경험 | 할 수 있는 일 |
|---|---|
| **선수 가상 대결 (EraMatch)** `/eramatch` | MLB/KBO/NPB 선택 → 시즌·선수·타석 수 → 결과·재생·계산 원리 |
| **AI 전략 연구 (Match)** `/match` | 학습 시작 → 선택 변화·상대 비교·장면 관찰 |

BaseballLab은 브랜드와 공통 통계 엔진입니다. 기존 `/baseball` 경로와 `project=baseball` 저장 결과는 MLB 대결로 계속 열립니다. 수집 자료가 있으면 기본 화면에서 MLB 2000~2025, KBO 1982~2026, NPB 2025를 선택합니다. 이전 과제·검증 모형은 개발자 정보의 **사용할 기록**에서 선택할 수 있고, 수집 자료가 없는 설치에서는 기존 기본 기록을 사용합니다. 원본과 저장 결과는 보존합니다.

현재 기준: [디자인 우선 지시](docs/specs/BaseballLab_Design_First_Codex_Directive.md).

## 시작하기

Python 3.11 이상을 설치하고 저장소 폴더에서 실행하세요.

```powershell
git pull origin main
python -m pip install -e ".[learning]"
python scripts/quickstart.py --open
```

서버가 이미 켜져 있으면 Ctrl+C로 종료한 뒤 다시 여세요.

- **선수 가상 대결 → 대결하기:** 같은 화면에서 MLB/KBO를 선택합니다. 결과는 핵심 수치·분포·타석 순서로 볼 수 있습니다. **계산 원리** 탭에서 선택한 선수의 기록과 보정·Log5·추첨 과정을 실제 숫자로 확인합니다. **개발자 정보**에는 설정·원천·재현·검증 근거가 있습니다.
- **AI 전략 연구 → 학습 시작:** 기간과 목표를 정해 학습하고, 저장 결과에서 선택 변화·성과·장면을 비교합니다. GPU 없이 실행할 수 있습니다. KBO 시즌 자료는 앱에 포함되어 있습니다.

기본 선수 대결은 수집 기록을 바로 사용합니다. MLB는 기록이 있는 8개 타석 사건을 구분하고 KBO·NPB는 누락된 피안타 종류를 채우지 않는 4개 공통 사건을 사용합니다. 계산 원리·예상과 이번 결과·타석 재생·같은 대결 재현에서도 실제 사용 사건을 유지합니다. 구분 가능한 기록이 없는 사건은 0개로 표시해 만들어내지 않습니다.

결과의 **실제 기록 살펴보기**에서 MLB 각 수집 시즌의 타구·투구 결과 코드, KBO 선수 계수와 2024년까지의 팀 주루·수비 표, NPB 원문 구속 예시를 볼 수 있습니다. NPB 좌표는 단위·기준 검증 전이므로 원문만 보여 줍니다. 팀 기록을 선수의 인과 효과나 AI의 가상 결과로 대입하지 않습니다. **야구 장면 살펴보기**에도 수집한 MLB 시즌 선택을 연결했습니다. **자료 관리**는 수집 원본·비공식 CSV·표준 집계·학습 전이를 표시하고 검증할 수 있습니다.

자료가 없으면 실제 준비 단계를 표시하고, 실패하면 이유와 재시도를 안내합니다. 다른 시즌이나 허구 선수로 대체하지 않습니다. 결과는 이 PC에 저장되고 각 프로젝트에서 다시 열 수 있습니다.

Match에서 **이닝 득점 전략** 또는 **득점 기회 전략**를 고르고 **AI 학습 시작**을 누릅니다. 새 이닝 연구는 무사·주자 없음에서 세 아웃까지 총득점을 보상으로 사용하며, 결과 요약에서 같은 상대에 대한 학습 전후 성적과 바뀐 선택을 봅니다. 기간의 앞 기록으로 모형을 만들고, 마지막 기록은 학습 종료 후에만 확인합니다.

**이닝 득점 전략 → 학습할 리그 환경**에서 MLB·KBO·NPB를 하나 또는 여러 개 선택하고 비중을 입력할 수 있습니다. MLB만 선택하면 기존 학습이며, KBO·NPB를 포함하면 리그별 실제 타석 빈도로 보정한 혼합 환경에서 하나의 정책을 학습합니다. 혼합 선택 시 사용 가능한 최근 MLB 시즌으로 기간을 맞춥니다. 기본 비중은 같고 자료가 많은 리그가 자동으로 더 많이 선택되지는 않습니다. 결과에는 리그별 실제 연습 횟수, 보정 자료 기간, 환경별 학습 전후 점수가 표시됩니다.

혼합 환경의 주자·아웃 전이는 MLB 관측 기록을 공통으로 쓴다는 **검증 전 운반 가정**입니다. KBO는 검사 시작 전에 완료된 시즌, NPB는 검사 시작일보다 앞선 정규시즌 관측 경기만 빈도 보정에 사용합니다. 시즌 합계를 가짜 KBO·NPB 경기 전이로 바꾸거나 서로 다른 리그의 수준이 같다고 인증하지 않습니다. 자세한 데이터 흐름은 [리그 혼합 학습 규칙](docs/league-data-contract.md#리그-환경-혼합-학습)을 확인하세요.

선수 대결 결과에는 **예상 개수와 이번 개수 그래프**, 장타·삼진 해석, 결과별 타석 찾기가 있습니다. MLB의 아웃·희생타·실책 세분은 실제 기록 구성에 따른 참고 추정입니다. KBO 시즌 합계로 구분할 수 없는 결과는 아웃으로 단정하지 않습니다.

일반 **대결 시작 / 다시 대결**은 매번 새 표본을 추첨합니다. 확률은 같은 조건에서 유지됩니다. **같은 대결 재현**은 당시 번호와 계산 조건을 사용해 타석 순서까지 복원하며, 저장 이력은 별도 실행으로 남습니다. 직접 번호를 지정하려면 세부 설정의 **번호를 고정해 재현하기**를 선택합니다. 저장 HTML은 웹의 결과 목록에서 열어 재실행할 수 있습니다.

Match 날짜는 선택한 시즌의 실제 기록 범위 안에서 고릅니다. 범위 초과·종료일 역전·3일 미만의 학습 기간은 시작 전에 안내하고 차단합니다. 화면 이동과 상태 확인은 자료를 읽거나 계산하는 동안에도 사용할 수 있습니다.

MLB 대결 결과의 **선수의 실제 타구·투구 기록 살펴보기**에서는 시즌의 타구 종류·첫 처리 수비 위치·투구 결과 순서를 봅니다. 이는 가상 대결의 궤적 예측과 구분합니다. 속도·발사각·구종·존 좌표는 현재 원천에 없습니다. [확인한 필드와 2025 추가 원본 수집](docs/data-contact-feasibility.md).

## Match 연구 결과는 어떻게 읽나요?

실제 저장 연구에서 **1,500번 중 704번(46.9%) 득점**, 나머지 796번은 차단됐습니다. **이 비율만으로 수비 AI가 더 잘한다고 판정하지 않습니다.** 공격과 수비가 맡은 과제가 비대칭이고 24개 시작 상황도 실제 경기 빈도와 다르기 때문입니다. 이전 버전의 50% 기준 ‘우세’ 해석은 철회했습니다.

같은 방식으로만 플레이하는 비교 상대에게는 수비 차단률이 **28.9% → 52.1%**로 좋아졌고, 공격의 개선은 확인되지 않았습니다. 숫자는 유지하고 해석을 바로잡았습니다.

새 결과 화면은 **바뀐 선택 / 같은 상대에 대한 바뀐 성과 / 아직 말할 수 없는 것**을 보여줍니다. 상황·학습 시점을 움직이며 선택 확률과 실제 누적 횟수를 구분하고, 같은 출발 상황의 저장 장면을 나란히 볼 수 있습니다. 이전 실행도 웹에서 새 화면으로 열립니다. 기존 JSON·저장 모델·HTML 원문은 덮어쓰지 않습니다.

[새 홈](docs/images/design-first/after-home.png) · [새 결과](docs/images/design-first/after-result.png) · [계산 원리](docs/images/design-first/after-principles.png) · [새 Match](docs/images/design-first/after-match.png) · [이전 첫 화면](docs/images/incremental/home-desktop.png) · [2023 대결](docs/images/incremental/baseball-2023.png) · [이전 세 프로젝트 화면](docs/images/three-projects/portal.png) · [통계 대결](docs/images/three-projects/baseball.png) · [시대 대결](docs/images/three-projects/eramatch.png) · [이전 첫 화면](docs/images/ux-home.png) · [야구 관람](docs/images/ux-field.png) · [AI 선택 변화](docs/images/ux-strategy.png)

## 자료는 어디에 있나요?

실제 수집 범위는 MLB **2000~2025년 4,925,133플레이**, KBO 공개 배포본 **1982~2026 선수 18,180행**과 팀·수비·주루 CSV, NPB 비공식 **CSV 98개·674,754행**입니다. NPB 2025 정규시즌으로 확인된 858경기는 1,002개 선수·역할·시즌 기록으로 집계했습니다. 중복 제공자를 합쳐 표본을 부풀리지 않습니다. 원본 범위·관측 단위·이용 조건은 [수집 현황](docs/data-collection-status.md)을 확인하세요.

```powershell
# 공식 원천에서 내려받기 (기존 검증된 자료는 재사용)
python scripts/collect_league_seasons.py --leagues MLB --start-year 2000 --end-year 2025
python scripts/collect_community_data.py
python scripts/collect_npb_community.py --prepare
# 확보한 전체 기간 / 리그별 최근 5시즌 선택
python scripts/prepare_league_data.py
python scripts/prepare_league_data.py --last-seasons 5
```

EraMatch의 **수집한 리그·시대의 공통 기록으로 비교하기**에서 MLB·KBO·비공식 NPB 자료를 같은 사건 정의로 비교합니다. Match 학습 화면에는 확보한 **전체 기간·최근 5시즌·개별 시즌** 선택이 나타납니다. 원본과 기존 집계의 검증값을 확인해 재사용하며, 기존 신경망 학습과 결과 화면으로 이어집니다. 시즌 합계로 구종 선택이나 투구 궤적을 만들지 않습니다. 결측값·최소 요건·보정 가정·출처별 결정은 [공통 자료 규칙](docs/league-data-contract.md)을 따릅니다. 공식 NPB 수집본의 제한과 비공식 배포본의 라이선스 선언은 별도로 취급합니다. 게시자의 라이선스는 upstream 권리·정확성의 독립 검증을 뜻하지 않습니다.

EraMatch 기본 자료는 앱 패키지에 포함된 대결용 시즌 집계입니다. 생년월일·학교·드래프트 항목과 원본 CSV/ZIP/코드/HWP는 포함하지 않습니다. [원본 대조·기본 자료 검증](docs/eramatch-default-data.md).

기존 통계 선수 카탈로그·과제 원본은 `data/local/catalog/`, 공식 경기 원본은 `data/local/retrosheet/`, 별도 사용자 투구 자료는 `data/local/statcast/`, 실행 결과는 `outputs/`에 보관합니다. **자료와 신뢰성** 화면에서 용량·분류·연결된 연구·원본 해시를 확인할 수 있습니다. 삭제는 대상과 재현성 영향을 확인하고 다시 동의한 경우에만 진행하며 자동 삭제하지 않습니다.

웹은 `127.0.0.1` 로컬 전용입니다. 앱 자체 암호화는 없으며 Windows 권한·백업·동기화의 안전을 확인했다고 주장하지 않습니다. 새 POSIX 저장 자료의 접근 권한을 제한하고, 공개 화면·로그의 로컬 경로와 인증정보를 가립니다. 원본과 가중치를 Git에 배포하지 않습니다.

[보안 확인·조치·미확인 목록](docs/security-audit.md) · [실행과 결과 읽기](docs/user-guide.md) · [개발 검증](docs/ux-validation.md)

Retrosheet 공식 [자료·열 정의·이용 고지](https://www.retrosheet.org/downloads/plays.html)를 확인하고 개별 URL·버전·해시를 등록해 사용합니다. 실제 관측, 그 기록에서 추정한 결과, AI 가상 장면, 미검증 가정과 테스트 입력을 구분합니다.

The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.

## 개발 검증

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/audit_repository.py
```

[통계 프로그램·공통 기반](docs/platform/README.md) · [AI 전략 연구](docs/match/README.md) · [자료](docs/data-sources.md) · [설계](docs/architecture.md)
