# Baseball AI Lab · 야구 AI 연구실

**승리만 추구하는 AI가 어떤 야구 전략을 발전시키는지 관찰하고, 실제 인간 야구와 비교하는 연구 플랫폼**입니다. 부모 패키지는 데이터·규칙·정책·학습·평가·기록·시각화를 공유하며 E01은 첫 타자·투수 경쟁 실험입니다.

개발 기준은 [PROJECT_VISION.md](PROJECT_VISION.md)의 **v4**입니다. 기존 임의 확률·능력·피로 모델을 연구 경로에서 제거했습니다. 이제 **실제 CSV 확보 → 품질 검사 → 기간 분리 보정·검증 → 제한된 경쟁 학습 → 근거가 연결된 화면** 순서로 실행합니다. 자료나 검증이 없으면 연구 실행을 보류하며 합성 자료로 대체하지 않습니다.

## 실행 — Windows PowerShell

복제한 저장소 폴더에서:

```powershell
git pull origin main
python -m pip install -e ".[learning]"

# 1. 공식 Statcast 2024-05-01~06 자료 확보·감사·기간 분리 보정/검증
python scripts/quickstart.py --mode prepare --open

# 2. 보정·검증이 통과한 실제 자료가 있을 때 학습
python scripts/quickstart.py --episodes 600 --open
```

Python 3.11 이상, NumPy만 추가 설치합니다. prepare의 첫 3일은 보정, 4일은 검증, 마지막 2일은 독립 최종 검증에 사용합니다. 수집은 최대 14일, 하루 단위 직렬 요청·캐시 보존이며 robots.txt의 접근 규칙을 확인합니다. 원본은 덮어쓰거나 GitHub에 재배포하지 않습니다. 공개 CSV라는 사실은 재배포 허가를 뜻하지 않습니다. [사용조건·출처 확인](docs/data-sources.md)을 참고하세요.

**이 클라우드에서는 공식 데이터 도메인이 프록시 정책으로 403 차단되어 실제 CSV를 확보하지 못했습니다.** 코드와 테스트·브라우저 동작은 검증했지만, 실데이터 모델 성능·실데이터 AI 학습 결과는 아직 없습니다. 로컬에서도 수집이 실패하면 오류를 확인하고 아래 공식 수동 내보내기 경로를 사용하세요.

### 공식 사이트에서 직접 내보낸 CSV 가져오기

Baseball Savant의 실제 검색 결과를 CSV로 내보낸 뒤 사용한 검색 URL, 획득 시각과 사용조건 확인 내용을 기록합니다. 파일을 프로그램이 스스로 진짜 원본이라고 보증하지 않으며 `user_attested_export`로 출처를 표시합니다.

```powershell
python scripts/quickstart.py --mode audit --csv "C:\Data\statcast.csv" --source-url "https://baseballsavant.mlb.com/statcast_search" --acquired-at "2026-11-04T23:00:00+09:00" --usage-note "확인한 사용조건과 수집 범위를 여기에 기록" --open
python scripts/quickstart.py --mode fit --train-before 2024-05-04 --test-from 2024-05-05 --open
python scripts/quickstart.py --episodes 600 --open
```

예시 획득 시각은 본인의 실제 획득 시각으로 바꾸세요. CSV에 세 기간의 날짜가 모두 있어야 합니다. 다른 기간은 `--start`, `--end`, `--train-before`, `--test-from`을 함께 맞추세요.

## 무엇을 볼 수 있나?

브라우저의 한국어 `report.html`에는 세 화면이 있습니다.

1. **한 구 관찰실:** 포수 시점 스트라이크존·도착 위치·구종·확인된 구속/회전, 사전 공개 상태·양쪽 정책 확률·실제 선택·결과. 이전/다음/재생/1배속/4배속, 체크포인트·기존 실행 seed 전환.
2. **전략 변화:** 실제 로그의 초구 스윙·구종 빈도, 같은 카운트의 정책 확률, 고정 상대·과거 모델 평가, N·구간·업데이트 수·정책 ID.
3. **현실 검증:** 별도 기간의 관측 결과·모델 기대 분포·모델 재추출 분포, 조건별 오차·희소 표본·도착 위치/구속 평균 비교, 원천 해시·필터·결측·모델·실행 ID.

위치 점을 선택하거나 세부정보를 열면 원본 투구 ID와 모델 버전을 확인할 수 있습니다. 실제 관측과 모델 생성은 다른 색·상태를 사용합니다. 자료가 없거나 결측인 값은 **데이터 없음**으로 남깁니다. 3D 궤적·사람의 속마음·미지원 수비 동작을 생성하지 않습니다.

결과는 `outputs/E01/research_<시각>/`, 원본·보정 자료는 `data/local/statcast/`에 저장됩니다. `--output`과 `--data-dir`로 바꿀 수 있습니다. 모델/로그는 각 원본 해시 및 로컬 경로에 결합되어 있으므로 다른 컴퓨터로 옮긴 경우 원본을 다시 가져와 보정하세요.

```powershell
# 검증만 확인
python scripts/quickstart.py --mode inspect --open

# 저장된 정책을 같은 데이터/모델에 연결해 다른 seed로 재생
python scripts/quickstart.py --mode replay --checkpoint "outputs/E01/실행폴더/checkpoints/pa_000600.json" --seed 42 --open
```

## 현재 연구 모델의 범위

모델은 **관측된 카운트·구종·위치 구간·스윙/테이크에 따른 실제 결과 빈도**로 보정합니다. 도착 위치는 타자의 선택과 독립적으로 재추출하고, 결과는 그 위치 구간과 선택을 조건으로 추정합니다. 희소 구간의 풀링과 남은 선택 편향을 공개합니다. 이는 인과효과가 입증된 전체 야구 물리 모델이 아닙니다.

최소 학습은 타자 스윙/테이크와 투수 구종 선택을 하는 두 신경망의 경쟁입니다. **보상은 출루(+1)/출루 저지(-1)의 명시된 타석 대리변수이며 경기 승리 보상이 아닙니다.** 궁극적 승리 목표는 유지하되, 근거 없는 주루·수비·능력·피로·번트 확률을 연결해 경기 승리 연구라고 부르지 않습니다. 컨택/파워 의도·목표 코스·선수 능력 탐색·전체 경기·KBO는 자료와 모델을 검증한 뒤 확장합니다.

## 개발·검증

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

테스트용 생성 자료는 `MOCK_TEST_ONLY`이고 연구 실행은 거부합니다. 테스트에서 양쪽 정책의 업데이트·재현·재생과 데이터/모델 무결성·기간 분리·실패 처리를 검사합니다. 기존 합성 모듈은 단위 테스트 전용이며, 과거 합성 샘플은 [감사 보관본](docs/archive/pre-v4/README.md)으로 이동했습니다.

[파일별 근거 감사](docs/data-audit-v4.md) · [보정·학습 설계](docs/learning.md) · [아키텍처](docs/architecture.md) · [개발 단계](docs/roadmap.md) · [v4 검증 기록](docs/v4-validation.md) · [상세 명세](docs/specs/Baseball_AI_Lab_VISUAL_REAL_DATA_SPEC.md)
