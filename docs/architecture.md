# 2026-11-11 공통 계약과 데이터 준비

`data.catalog.DatasetCatalog`가 기존 물리 저장소 위에서 `describe/get/ensure`를 제공합니다. BaseballLab·EraMatch·Match CLI/외부 평가는 같은 등록 제공원을 사용하며, 유효한 보관 파일은 다시 쓰지 않습니다. `simulation.contracts`는 선수-시즌 분모와 전체 확률·실행 메타데이터를 검증합니다. 독립 타석과 상태가 이어지는 장면 기록은 `mode`로 구분하며, 장면에 없는 확률을 만들지 않습니다.

`web.server`는 공식 기록 준비를 별도 작업으로 실행하고, 상태 조회·진행·취소를 기존 단일 작업 경계 안에 통합합니다. 같은 준비 요청은 하나로 합치며 이미 있는 자료는 무쓰기 반환합니다. Host/Origin/token과 고정 제공원·경로·삭제 확인을 보존합니다. 기록·모델·난수 고급 설정은 기본 화면에서 숨기고 실제 자동 선택 이유를 설명합니다.

[현재 검증](incremental-redesign-validation.md) · [데이터 계약](data-provider-review.md) · [통계 검사](model-independent-validation.md) · [다음 Match 계약](match/next-tactical-study.md).

아래는 2026-11-09까지의 구조 이력입니다. 물리 저장소와 기존 결과 형식은 보존합니다.

---

# 현재 화면·자료 경계

공통 2D 장면 렌더러를 관람과 Match 비교 화면에서 재사용합니다. 연구자의 사적 계보는 디스크에 보존하고 표시용 사본만 가립니다. 자료 관리는 고정된 보관 영역과 두 번 확인하는 삭제 절차로 분리했습니다. [현재 상태](PROJECT_STATUS.md) · [보안 점검](security-audit.md)

---

# 현재 세 프로그램과 공유 엔진

`/baseball`은 통계 선수 대결, `/eramatch`는 KBO 과제 웹화, `/match`는 AI 경쟁 학습·인간 비교다. 홈 `/`에서 각각 진입하며 자료 관리는 `/lab/data`를 공유한다. 기존 R1 관찰 `/simulation`, 학습 `/match/team`, 투구 준비 `/match/at-bat` 경로를 보존했다.

`matchup.catalog/mlb` → 고유 ID·시즌 선수 프로필 → `matchup.models`의 원본 재현/다항 Log5 → `matchup.service` 반복 타석 → 공유 `web/matchup.html`의 왼쪽 실행/오른쪽 맥락 설명과 저장 결과로 연결한다. 과제 전용 계산을 EraMatch 아래 복제하지 않는다. 원본 SHA·자료 ID·코드 지문·모델·재현 번호·반복을 실행별로 남긴다.

Match 학습/보고는 `experiments/match/`가 소유한다. 공통 신경망과 기존 경험 전이를 재사용하며 새 통계 모델의 예측 검사를 행동 변경의 인과 효과로 간주해 자동 연결하지 않는다. `r1.training/report`는 호환 경로다. [책임 표](platform/README.md) · [이번 검증](three-project-validation.md).

이하 이전 구현 설명을 보존합니다. 과거의 `r1.training` 구현 본문은 현재 Match 모듈로 이관됐습니다.

---

# 현재 기본 E01-R1 경로

`r1.provider`(공식 ZIP·고지·해시·캐시) → `r1.data`(관측 턴 정규화·연속성) → `r1.environment`(기간 분리·지원 행동·경험 전이·득점 상황 종료) → `r1.training`(공통 신경망·과거 상대·독립 환경 평가) → `r1.report`(한국어 기록·그래프·턴 재생).

부모의 `agents.neural.NeuralPolicy`, 출처/해시/파일 저장 유틸리티, CLI, 웹 실행·중지·보고서 경로를 재사용한다. 신경망은 행동·사전 특징·스키마를 주입하며 상태별 지원 행동 마스크를 경사에도 적용한다. 임의 경기 결과 모델을 연구로 재사용하지 않는다. R1은 E01의 제한된 실험이며, 공통 엔진에 Retrosheet 전용 규칙을 전역으로 강제하지 않는다. E02는 아직 구현하지 않는다.

`r1-outs-bases-public-v1`, `r1-observed-turn-versus-intentional-walk-v1` 스키마는 기존 카운트·구종 정책과 구분한다. 실제 donor ID와 가상 장면의 분류를 나누며, 공식 CSV의 플레이 번호/행 번호까지 추적한다. 원본·모델·가중치·실행 결과는 Git에 넣지 않는다.

이하 기존 Statcast 경로는 별도 선택지로 유지한다.

---

# v4 부모 플랫폼과 자식 실험

```text
공식 CSV / 사용자 공식 내보내기
 → data.statcast: 원본·계보·품질·단위·정규화
 → outcome.empirical: 기간 분할·조건부 빈도·풀링·독립 검증
 → 연구 진입 검사 (실제 자료 / 무결성 / 지원·검증 기준)
 → research.environment: 공통 타석 규칙 + 경험적 모델
 → research.training: 재사용 신경망·경쟁 학습·과거 상대·체크포인트
 → research.replay / tracking.evidence_report: 실행 로그·관측·검증 2D 화면
```

현재 E01의 dataset/model/run ID는 분리되어 있다. 새 자식은 같은 data/outcome/policy/environment/evaluation 계약을 재사용하며, 규칙을 복사하지 않는다. `NeuralPolicy`는 행동 목록·특징 함수·관측/행동 버전을 주입받는다. 기존 core.engine.transition의 볼넷/삼진/파울/타석 종료 규칙을 재사용한다.

원천과 추정, 모델 생성, 미검증 가정, 테스트 입력은 SourceStatus로 구별한다. DataLineage에는 URL·획득 방법·시각·원본 SHA·필터·N·결측·단위·사용조건을 보존한다. 모델에는 fit/validation/test의 날짜·게임/투구 ID, 설정·검증 오차·미지원 항목을 포함한다. 실행에는 코드·환경·seed·상대 풀·체크포인트·각 배치 정책 버전을 기록한다.

각 event는 run/event/episode ID, 사전 두 관측, 정책 ID·선택 확률·행동, 실제 사용한 결과 확률·N·구간·풀링, donor 투구 ID, 데이터/모델 버전, 사건·대리보상을 보존한다. 실제 관측과 재추출 좌표를 같은 상태로 표시하지 않는다. 자기결정과 실제 인간의 속마음도 혼동하지 않는다.

v4 스키마는 statcast-normalized-v1, statcast-observational-pa-v2, empirical-count-v1, empirical-take-swing-pitchtype-v1, empirical-pa-policies-v1이다. 구종 순서·특징·모델·데이터 버전이 다른 저장 정책은 거부한다.

기존 synthetic/game 결과 모델과 타석/경기 테스트를 보존했지만 연구 CLI는 호출하지 않는다. 기존 합성 학습·실행/재평가 함수는 test_only 없이 실행할 수 없다. 기존 샘플은 docs/archive/pre-v4에서 연구 근거 제외 표시로 보관한다.

## 화면

외부 웹 서버나 CDN 없이 로컬 HTML을 생성한다. A 한 구 관찰: 스트라이크존, 실제/모델 레이어, 정책 관측·확률, 제어·체크포인트·기존 seed. B 전략 변화: 로그 빈도·고정 카운트 정책·평가 N/구간·상대 풀. C 현실 검증: 실제 보류 표본과 기대/재추출 분포, 조건별 오차·센서 평균 비교. 미지원 값은 빈 패널·사유로 표시한다.

실데이터가 없으면 같은 화면에 DATA_REQUIRED 상태만 생성한다. UI 테스트의 MOCK_TEST_ONLY 기록은 테스트 디렉터리에만 만들고 연구 결과로 복사하지 않는다. 연구 결과 파일을 덮어쓰지 않도록 새 output 디렉터리를 사용한다.

## 웹 실행실

`web.server`는 127.0.0.1에서만 동작하는 표준 라이브러리 HTTP 서버다. `web/workbench.html`이 업로드·모델 검사·학습·중지·진행·보고서 열기를 제공한다. 명령은 고정된 Python CLI 인수 목록으로만 구성하고 shell을 사용하지 않는다. 외부 Origin/Host 요청·토큰 없는 변경 요청·결과 디렉터리 밖 경로를 거부한다. 한 번에 하나의 작업만 수행하고 매 실행을 별도 폴더에 남긴다. 실제 실행 체크포인트 로그로만 진행을 표시하며, 서버 재시작 후 미완료 실행을 완료로 바꾸지 않는다.
