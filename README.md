# BaseballLab · 야구 연구실

실제 경기 기록을 바탕으로 야구 장면을 보고, AI가 상대를 만나며 어떤 선택을 바꾸는지 연구합니다. **경기 승리를 추구하는 전략의 진화**가 장기 목표이며, 현재 실행 범위는 **3아웃 전에 한 점을 만들고 막는 실험**입니다.

프로젝트의 우선 방향은 [Project Compass](docs/PROJECT_COMPASS.md)를 따릅니다. [현재 상태](docs/PROJECT_STATUS.md)에서 작동·검증된 범위와 남은 연구를 구분합니다.

## 시작하기

Python 3.11 이상을 설치하고 저장소 폴더에서 실행하세요.

```powershell
git pull origin main
python -m pip install -e ".[learning]"
python scripts/quickstart.py --open
```

서버가 이미 켜져 있으면 Ctrl+C로 종료한 뒤 다시 여세요. 브라우저 첫 화면에서 두 활동을 고릅니다.

- **야구 장면 보기:** 실제 기록 또는 기록 기반 가상 공격을 야구장 그림으로 살펴봅니다. 여기서는 새 AI를 학습하지 않습니다.
- **실험 설정하기:** 공식 기록을 자동 준비하고 두 AI를 학습합니다. 같은 상황에서 학습 전·중간·이후의 선택과 성과를 비교합니다.

기본은 2024년 기록으로 3,000번씩 난수만 바꾸어 3회 반복합니다. CSV를 직접 구할 필요가 없고 GPU도 필요하지 않습니다. 2023년 독립 시즌 확인도 별도로 제공합니다. 구종·목표 코스·개별 스윙, 9이닝 전체 승부와 KBO 비교는 아직 준비 중입니다.

## 결과는 어떻게 읽나요?

실제 저장 연구에서 **1,500번 중 704번(46.9%) 득점**, 나머지 796번은 차단됐습니다. **이 비율만으로 수비 AI가 더 잘한다고 판정하지 않습니다.** 공격과 수비가 맡은 과제가 비대칭이고 24개 시작 상황도 실제 경기 빈도와 다르기 때문입니다. 이전 버전의 50% 기준 ‘우세’ 해석은 철회했습니다.

같은 방식으로만 플레이하는 비교 상대에게는 수비 차단률이 **28.9% → 52.1%**로 좋아졌고, 공격의 개선은 확인되지 않았습니다. 숫자는 유지하고 해석을 바로잡았습니다.

새 결과 화면은 **바뀐 선택 / 같은 상대에 대한 바뀐 성과 / 아직 말할 수 없는 것**을 보여줍니다. 상황·학습 시점을 움직이며 선택 확률과 실제 누적 횟수를 구분하고, 같은 출발 상황의 저장 장면을 나란히 볼 수 있습니다. 이전 실행도 웹에서 새 화면으로 열립니다. 기존 JSON·저장 모델·HTML 원문은 덮어쓰지 않습니다.

[첫 화면](docs/images/ux-home.png) · [야구 관람](docs/images/ux-field.png) · [AI 선택 변화](docs/images/ux-strategy.png)

## 자료는 어디에 있나요?

공식 원본은 `data/local/retrosheet/`, 별도 사용자 투구 자료는 `data/local/statcast/`, 실행 결과는 `outputs/`에 보관합니다. **자료와 신뢰성** 화면에서 용량·분류·연결된 연구·원본 해시를 확인할 수 있습니다. 삭제는 대상과 재현성 영향을 확인하고 다시 동의한 경우에만 진행하며 자동 삭제하지 않습니다.

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

[부모 플랫폼](docs/platform/README.md) · [AI 전략 연구](docs/match/README.md) · [자료](docs/data-sources.md) · [설계](docs/architecture.md)
