# Baseball AI Lab · 야구 AI 연구실

**승리만 추구하는 AI가 어떤 야구 전략을 스스로 발전시키는지 관찰하고, 인간 야구의 역사·현대 전략과 비교하는 부모 연구 플랫폼**입니다. 첫 자식 E01은 타자·투수의 경쟁 학습, 후속 E02는 MLB/KBO에서 독립 학습한 정책의 교차 대결입니다.

지금 기본 실행은 **실제 신경망 강화학습**입니다. 타석 통계만 출력하던 기준선 비교는 `--mode baseline`으로 별도 실행합니다.

## 실행 — Windows PowerShell

이미 복제한 `BaseballLab-git` 폴더에서 실행하세요. Python 3.11 이상이 필요합니다.

```powershell
git pull origin main
python -m pip install -e ".[learning]"
python scripts/quickstart.py --open
```

처음 내려받는 경우 `git clone https://github.com/larus-harir/BaseballLab.git` 후 해당 폴더로 이동하세요. NumPy만 추가 설치하며, GPU나 PyTorch는 필요하지 않습니다.

기본으로 **600번의 3이닝 경기**를 학습합니다. 경기 종료 시 승리 `+1`, 패배 `-1`, 무승부 `0`만 보상으로 사용하고, 중간 타격 성적·득점·삼진·특정 전략을 보상하지 않습니다. 200경기마다 같은 상대·같은 평가 시드·선후공 교환으로 평가합니다. 완료 후 한국어 HTML 보고서가 브라우저에서 열립니다.

보고서에서는 다음을 볼 수 있습니다.

- 학습 전부터 각 세대까지의 고정 상대 평가 성적.
- **같은 경기 상황에서** 기다리기·컨택·강공·번트 선택 확률의 변화.
- 구종·존 공략/유인구·투구 강도 선택 변화.
- 학습된 팀의 평가 경기 재생: 투구별 행동, 주자·아웃·점수 변화.

```powershell
# 더 오래 학습 / 9이닝 경기 / 재현할 seed
python scripts/quickstart.py --games 5000 --innings 9 --seed 42 --open

# 결과 위치 지정 — 기존 학습을 덮어쓰지 않도록 새 폴더 사용
python scripts/quickstart.py --games 1200 --evaluation-pairs 32 --output outputs/E01/my_run --open

# 저장된 모델을 새 학습 없이 재평가하고 경기 재생
python scripts/quickstart.py --mode replay --checkpoint outputs/E01/my_run/checkpoints/game_001200.json --output outputs/E01/review --open
```

`--open` 없이 실행하면 마지막에 출력되는 `report.html` 경로를 직접 여세요. 기본 결과 폴더는 `outputs/E01/학습_<실행시각>/`입니다. `training.json`에 전체 이력·설정·시드·환경 버전, `checkpoints/`에 타자·투수 신경망 가중치, `replay.json`에 재생 기록이 저장됩니다.

## AI가 선택하는 것

| 타자 | 투수 | 공개 관측 |
|---|---|---|
| 기다리기·컨택·강공·번트 | 직구·변화구·체인지업 × 존/유인구 × 절약/보통/전력 투구 (18조합) | 카운트·주자·아웃·이닝·점수 차·선후공·누적 투구 부하 |

각 역할은 **은닉층 2개의 작은 신경망**으로 확률적 행동을 선택하며, 경기 종료 보상에 대한 정책경사(REINFORCE)로 가중치를 갱신합니다. 과거의 자기 모델들과 고정 기준선을 상대하며 타격·투구 두 정책을 함께 학습합니다. 특정 플레이스타일을 선택하도록 정답 레이블을 주지 않습니다. 타자는 현재 투구의 구종·코스를 미리 관측하지 못합니다.

공격/수비·주루의 모든 동작을 학습하는 완성형 야구 AI는 아직 아닙니다. 현재는 동질 선수, 자동 수비·보수적인 진루, 간이 병살·번트·투수 피로를 가진 합성 경기입니다. **실제 리그로 보정되지 않은 모델을 공략하는 현상**도 생길 수 있습니다. 이를 발견하고 데이터·규칙·평가로 검증하는 것이 다음 연구의 일부입니다. 한 번의 승률 상승이나 선택 변화만으로 실제 야구의 최적 전략을 발견했다고 결론내리지 않습니다.

[실제 1,200경기 학습 기록](experiments/E01_batter_pitcher_evolution/reports/learning-validation.md) · [학습·경기 설계](docs/learning.md)

## 기존 기준선 시뮬레이션

이 명령은 외부 패키지 없이 실행됩니다. 고정 전략을 비교하는 용도이며 학습하지 않습니다.

```powershell
python scripts/quickstart.py --mode baseline
python scripts/quickstart.py --mode baseline --seeds 1 2 3 --plate-appearances 1000 --output outputs/E01/baselines
```

한국어 대결표·요약, 상세 JSON, 투구별 CSV를 저장합니다.

## 개발·테스트

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

가상환경을 사용하려면 먼저 `python -m venv .venv`를 실행하고 해당 환경의 Python을 사용하세요. 개발 설치 후 `python -m baseball_lab`과 `baseball-lab`도 같은 CLI를 제공합니다. GitHub Actions는 Python 3.11–3.13 / Ubuntu·Windows에서 테스트와 기준선·학습 실행을 검사하도록 설정했습니다.

## 부모 플랫폼과 자식 실험

| 모듈 | 역할 |
|---|---|
| `core` | 타석 규칙 + 주자·득점·이닝·승패 경기 엔진, 공개 관측·행동 |
| `outcome` | 교체 가능한 확률 결과 모델·능력·피로·투구 강도 |
| `agents` | 정책 계약, 기준선·신경망, 메타데이터·스키마 검사 |
| `training` | 승패 보상 학습, 과거 상대 풀, 체크포인트 |
| `evaluation` | 고정 조건·선후공 교환 평가, 학습과 독립된 재평가 |
| `tracking` | 행동 변화·대결 결과·재생·한국어 HTML 보고서 |
| `data` | 출처·버전과 공통 이벤트 스키마; 실제 리그 어댑터 확장 위치 |
| `experiments/E01_batter_pitcher_evolution` | 자식 실험 E01의 설명·설정·검증 기록 |
| `experiments/E02_mlb_vs_kbo` | 리그별 데이터 가용성·공정성·교차 평가 설계 |

[아키텍처](docs/architecture.md) · [개발 단계](docs/roadmap.md) · [연구 원칙](docs/research-principles.md) · [데이터 계획](docs/data-sources.md) · [원본 설계서](docs/specs/Baseball_AI_Lab_Master_Handoff.md)
