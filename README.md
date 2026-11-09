# BaseballLab · 야구 연구실

실제 기록으로 선수 대결을 실행하고 AI 전략의 변화를 연구하는 세 프로젝트입니다. **BaseballLab 자체도 실행 가능한 통계 시뮬레이터**이며, 공통 기반만을 뜻하지 않습니다.

| 프로젝트 | 클릭해서 할 수 있는 일 | 현재 한계 |
|---|---|---|
| **BaseballLab** `/baseball` | MLB 선수 선택 → 확률 계산 → 반복 타석 → 계산 설명 | 2024 정규시즌, 독립 타석. AI 학습·9이닝 경기 아님 |
| **Match** `/match` | AI 학습 → 같은 상대 성과·전략 변화·장면 비교 | 현재 3아웃 전 한 점 실험. 인간의 현대·역사 전략 비교는 이 연구의 후속 단계 |
| **EraMatch** `/eramatch` | KBO 선수·연도 → 시대 보정 → 25타석 → 원본/개선 후보 비교 | 사용자 과제 자료 기반, 원천·권한·시대 보정의 예측 검증 전 |

현재 역할 정의는 [최신 요구사항](docs/specs/BaseballLab_Three_Project_Redefinition_Codex.md), [길잡이](docs/PROJECT_COMPASS.md), [실행·검증 보고](docs/three-project-validation.md)를 따릅니다. 이전 문서의 ‘부모는 공통 기능만’ 정의는 대체했습니다.

## 시작하기

Python 3.11 이상을 설치하고 저장소 폴더에서 실행하세요.

```powershell
git pull origin main
python -m pip install -e ".[learning]"
python scripts/quickstart.py --open
```

서버가 이미 켜져 있으면 Ctrl+C로 종료한 뒤 다시 여세요. 브라우저에서 세 프로젝트 중 하나를 선택합니다.

- **BaseballLab → 선수 대결 실행:** 최초에는 **공식 MLB 기록 자동 준비**를 누릅니다. 이후 실제 선수 이름을 검색하고 **확률 계산하고 대결 실행**을 누르세요. 오른쪽 패널에서 선택의 원본 기록·보정·Log5 중간값을 봅니다.
- **Match → 실험 설정하기:** 공식 기록을 자동 준비하고 AI를 학습합니다. 기본은 2024 기록으로 3,000회씩 3회 반복이며 GPU가 필요하지 않습니다. 기존 장면 관찰은 `/simulation`에 보존했습니다.
- **EraMatch → 시대 대결 실행:** 이 환경에는 제공한 원본 과제를 연결했습니다. 새 PC는 원본 **code.zip**을 처음 한 번 연결해야 합니다. 라이선스가 확인되지 않은 CSV를 Git으로 배포하거나 임의 다운로드하지 않습니다. 이름·연도를 고르고 기본 **25타석**을 실행하세요. 개선 후보와의 차이도 확인할 수 있습니다.

자료가 없으면 준비 안내만 표시하며 허구의 선수나 실행 결과를 만들지 않습니다. 결과는 이 PC에 저장되고 각 프로젝트에서 다시 열 수 있습니다.

## Match 연구 결과는 어떻게 읽나요?

실제 저장 연구에서 **1,500번 중 704번(46.9%) 득점**, 나머지 796번은 차단됐습니다. **이 비율만으로 수비 AI가 더 잘한다고 판정하지 않습니다.** 공격과 수비가 맡은 과제가 비대칭이고 24개 시작 상황도 실제 경기 빈도와 다르기 때문입니다. 이전 버전의 50% 기준 ‘우세’ 해석은 철회했습니다.

같은 방식으로만 플레이하는 비교 상대에게는 수비 차단률이 **28.9% → 52.1%**로 좋아졌고, 공격의 개선은 확인되지 않았습니다. 숫자는 유지하고 해석을 바로잡았습니다.

새 결과 화면은 **바뀐 선택 / 같은 상대에 대한 바뀐 성과 / 아직 말할 수 없는 것**을 보여줍니다. 상황·학습 시점을 움직이며 선택 확률과 실제 누적 횟수를 구분하고, 같은 출발 상황의 저장 장면을 나란히 볼 수 있습니다. 이전 실행도 웹에서 새 화면으로 열립니다. 기존 JSON·저장 모델·HTML 원문은 덮어쓰지 않습니다.

[새 세 프로젝트 화면](docs/images/three-projects/portal.png) · [통계 대결](docs/images/three-projects/baseball.png) · [시대 대결](docs/images/three-projects/eramatch.png) · [이전 첫 화면](docs/images/ux-home.png) · [야구 관람](docs/images/ux-field.png) · [AI 선택 변화](docs/images/ux-strategy.png)

## 자료는 어디에 있나요?

통계 선수 카탈로그·과제 원본은 `data/local/catalog/`, 공식 경기 원본은 `data/local/retrosheet/`, 별도 사용자 투구 자료는 `data/local/statcast/`, 실행 결과는 `outputs/`에 보관합니다. **자료와 신뢰성** 화면에서 용량·분류·연결된 연구·원본 해시를 확인할 수 있습니다. 삭제는 대상과 재현성 영향을 확인하고 다시 동의한 경우에만 진행하며 자동 삭제하지 않습니다.

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
