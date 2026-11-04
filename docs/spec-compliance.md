# 원본 문서와 구현 대조

기준은 사용자 제공 [Master Handoff](specs/Baseball_AI_Lab_Master_Handoff.md)와 [Codex Start Prompt](specs/Baseball_AI_Lab_Codex_Start_Prompt.md)이다. 원본을 저장소에 함께 보존했다.

초기 커밋은 부모/자식 디렉터리와 실행 가능한 타석 규칙을 갖췄지만, 공통 평가가 고정 기준선을 직접 생성하고 기록기가 E01에 결합되어 있었다. 메타데이터 호환성 검사도 실제 평가 경로에서 호출하지 않았다. 이번 보완에서 이를 수정했다.

| 수락 요구사항 | 실제 구현·검증 근거 |
|---|---|
| 부모 플랫폼 + 독립 자식 E01 | 공통 패키지 / E01 README·JSON·run.py, 실험 레지스트리 |
| 공통 엔진 재사용, 리그 하드코딩 없음 | RuleSet/LeagueProfile/OutcomeModel 주입, 다른 프로파일·정책·실험 ID로 동일 실행기 테스트 |
| 규칙·확률 분리 | core/engine.py와 outcome/synthetic.py, 경계·확률 검증 |
| 관측 누수 방지 | 정책에는 count-v1만 전달, 결과 모델에만 현재 투구·OutcomeContext 전달, 테스트 |
| 기준선 3 × 3 대결 | random/aggressive/patient × random/strike_first/mixed, 기본 9,000타석 |
| 설정·seed·결과·행동 비율 기록 | JSON/대결 CSV/투구별 CSV/요약 Markdown, 카운트별 행동·구종·위치 |
| 재현성 | 역할·타석별 독립 RNG, seed 목록 반복 평가, 동일 실행 결과 테스트 |
| 비호환 정책 거부 | 실제 evaluate → registry.resolve → metadata.validate_compatibility 경로 검증 |
| 간단한 설치·실행 | 외부 런타임 패키지 없이 quickstart, 개발 설치 후 모듈/CLI 실행 |
| 유효한 실행 결과·샘플 | tests, docs/m1-validation.md, E01 reports/m1-baseline-sample.md |
| E02 확장과 데이터 한계 | experiments/E02_mlb_vs_kbo/README.md, docs/data-sources.md |
| 장기 연구 목적 유지 | docs/research-principles.md와 roadmap.md: 경기 승리 보상·전략 관찰·인간 기록 비교 |

이 표는 M0/M1 기준선 요구사항의 대조다. 기준선 실행은 `--mode baseline`에서 유지한다. 현재 기본 실행은 경기 승패 기반 신경망 학습이며 [학습 설계](learning.md)에 구현·검증 범위를 기록했다. 합성 경기 학습을 실제 리그 전략 검증 완료로 보고하지 않는다. 전체 경기와 학습의 구현 상태는 개발 단계에 명시하며, 삼진·타율·OPS 같은 관찰 지표를 보상 정답으로 만들지 않는다.
