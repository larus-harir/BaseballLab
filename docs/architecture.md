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

v4 스키마는 statcast-normalized-v1, statcast-observational-pa-v1, empirical-count-v1, empirical-take-swing-pitchtype-v1, empirical-pa-policies-v1이다. 구종 순서·특징·모델·데이터 버전이 다른 저장 정책은 거부한다.

기존 synthetic/game 결과 모델과 타석/경기 테스트를 보존했지만 연구 CLI는 호출하지 않는다. 기존 합성 학습·실행/재평가 함수는 test_only 없이 실행할 수 없다. 기존 샘플은 docs/archive/pre-v4에서 연구 근거 제외 표시로 보관한다.

## 화면

외부 웹 서버나 CDN 없이 로컬 HTML을 생성한다. A 한 구 관찰: 스트라이크존, 실제/모델 레이어, 정책 관측·확률, 제어·체크포인트·기존 seed. B 전략 변화: 로그 빈도·고정 카운트 정책·평가 N/구간·상대 풀. C 현실 검증: 실제 보류 표본과 기대/재추출 분포, 조건별 오차·센서 평균 비교. 미지원 값은 빈 패널·사유로 표시한다.

실데이터가 없으면 같은 화면에 DATA_REQUIRED 상태만 생성한다. UI 테스트의 MOCK_TEST_ONLY 기록은 테스트 디렉터리에만 만들고 연구 결과로 복사하지 않는다. 연구 결과 파일을 덮어쓰지 않도록 새 output 디렉터리를 사용한다.
