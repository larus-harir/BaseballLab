# Baseball AI Lab

**승리만 추구하는 AI가 어떤 야구 전략을 스스로 발전시키는지 관찰하고, 인간 야구의 역사·현대 전략과 비교하는 연구 플랫폼**입니다.

부모 패키지는 규칙·확률 모델·정책·데이터 형식·대결·기록을 공유합니다. 첫 자식 **E01 Batter vs Pitcher Evolution**은 타자와 투수의 경쟁 연구이며, **E02 MLB-trained vs KBO-trained**는 같은 기반에서 독립 학습 정책을 교차 평가할 후속 실험입니다.

현재 실행 가능한 단계는 E01의 타석 시뮬레이션입니다. 기준선 9개 조합의 결과와 전략 선택을 기록합니다. 확률은 합성 모델이며, 실제 리그 자료 보정·전체 경기·승리 보상·경쟁 학습은 [개발 단계](docs/roadmap.md)에 따라 연결합니다.

## 바로 실행하기

Python 3.11 이상이면 추가 설치 없이 실행됩니다.

```bash
git clone https://github.com/larus-harir/BaseballLab.git
cd BaseballLab
python scripts/quickstart.py
```

이미 내려받았다면 `git pull origin main` 후 마지막 명령을 실행하세요. Linux에서 `python`이 없으면 `python3`, Windows에서는 `py`를 사용할 수 있습니다.

터미널에 타자·투수 조합별 타석 수, 볼넷 비율, 삼진 비율, 초구 스윙 비율이 나옵니다. 기본 설정은 seed `20261104`, 9조합 × 1,000타석입니다.

결과는 `outputs/E01/`에 저장됩니다.

| 파일 | 확인할 내용 |
|---|---|
| `summary.md` | 읽기 쉬운 대결 요약·매치업 행렬·지표 설명 |
| `results.json` | seed별 결과, 정책 버전, 카운트별 행동·구종, 확률 구간, 설정·코드 식별 정보 |
| `matchups.csv` | 엑셀로 볼 수 있는 조합별 결과·행동 비율 |
| `pitches.csv` | 매 투구의 카운트·타자 행동·투수 선택·사건·타석 종료 결과 |

같은 결과 폴더를 지정하면 해당 실행 파일을 갱신합니다. 다른 실행을 보존하려면 `--output`을 바꾸세요. 시뮬레이션이 실패하면 이전의 완성된 결과 파일을 유지합니다.

```bash
# 3개 seed로 반복 평가: 27개 대결, 총 27,000타석
python scripts/quickstart.py --seeds 20261104 20261105 20261106 --output outputs/E01/repeat

# 타석 수 변경 / 설정 파일 사용 / 실험 목록
python scripts/quickstart.py --plate-appearances 100
python scripts/quickstart.py --config experiments/E01_batter_pitcher_evolution/configs/m1_baseline.json
python scripts/quickstart.py --list
```

작은 실제 실행 샘플은 [E01 검증 리포트](experiments/E01_batter_pitcher_evolution/reports/m1-baseline-sample.md)에 있습니다.

## 개발·테스트

```bash
python -m venv .venv
# Linux/macOS
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
# Windows
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

개발 설치 후 가상환경에서 `python -m baseball_lab` 또는 `baseball-lab`도 같은 CLI를 제공합니다. 외부 데이터, DB, GPU, 웹 서버 없이 실행됩니다. 현재 로컬 검증은 Python 3.12의 **69개 테스트 통과**이며, GitHub Actions에는 Python 3.11–3.13 / Ubuntu·Windows 검증을 설정했습니다.

## 부모와 자식의 역할

| 경로 | 역할 |
|---|---|
| `src/baseball_lab/core/` | 합법 행동, 공개 관측, 타석 상태 전이, 규칙·프로파일·선수 능력 계약 |
| `src/baseball_lab/outcome/` | 상태·능력을 전달받는 교체 가능한 확률 결과 모델 |
| `src/baseball_lab/agents/` | 정책 인터페이스, 기준선, 정책 레지스트리·버전·스키마 검사 |
| `src/baseball_lab/data/` | 출처·버전이 있는 공통 투구 이벤트 스키마 |
| `src/baseball_lab/evaluation/` | 임의의 등록 정책 간 대결, 카운트별 집계, 통계 |
| `src/baseball_lab/tracking/` | 공통 JSON/CSV 기록, 투구별 스트리밍, Markdown 리포트 |
| `src/baseball_lab/experiments/` | 설정 검증, 실험 목록, 공통 실행기 |
| `src/baseball_lab/training/` | 후속 학습 루프의 모듈 위치 |
| `experiments/E01_batter_pitcher_evolution/` | E01 가설·설정·실행 입구·샘플 |
| `experiments/E02_mlb_vs_kbo/` | E02의 데이터·평가 설계 |

[아키텍처·실험 추가 방법](docs/architecture.md) · [원본 설계서](docs/specs/Baseball_AI_Lab_Master_Handoff.md) · [요구사항 대조](docs/spec-compliance.md) · [실행 검증](docs/m1-validation.md) · [연구 원칙](docs/research-principles.md) · [데이터 계획](docs/data-sources.md)
