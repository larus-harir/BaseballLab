# v4 파일별 근거 감사

우선 기준은 [프로젝트 헌장 v4](../PROJECT_VISION.md)와 [시각화·실데이터 명세](specs/Baseball_AI_Lab_VISUAL_REAL_DATA_SPEC.md)다.

| 코드/항목 | 감사 분류 | 조치 |
|---|---|---|
| outcome/synthetic.py의 구종별 접촉률·안타 구성·타자 능력 계수 | UNVERIFIED_ASSUMPTION | 연구 실행 경로에서 제거, 기존 로직 검증용으로만 유지 |
| outcome/game.py의 제구/피로/강도/번트/땅볼 수치 | UNVERIFIED_ASSUMPTION | v4 모델에서 사용하지 않음 |
| core/game.py의 보수적 진루·병살 확률 | UNVERIFIED_ASSUMPTION | 전체 경기 연구 미지원, 단위 테스트에서만 사용 |
| core/engine.py의 카운트·타석 종료 | 규칙 기반 | 공통 엔진으로 유지, 단위 테스트 |
| agents/neural.py의 학습률·층 크기·옵티마이저 | 실험 설정 | 야구 능력/확률로 취급하지 않음, 설정·버전 보존 |
| 기존 학습·타석 실행기 | 합성 실행 | test_only 명시 없으면 차단, 연구 CLI에서 호출하지 않음 |
| 기존 HTML/CSV 샘플 | 실제 실행됐지만 합성 환경의 로그 | docs/archive/pre-v4로 이동, 연구 근거에서 제외 |
| 실제 인간의 컨택/파워 의도·투구 목표 코스 | 미관측 | 자료에서 추정해 채우지 않음, 미지원 |
| 실제 선수 능력·피로·3D 궤적·수비 이동 | 미검증/미구현 | 연구용 화면에 숫자·애니메이션 생성 안 함 |
| data/statcast.py의 원천 | REAL_OBSERVED 후보를 검사 | 공식 HTTPS 수집 또는 사용자 공식 CSV 내보내기, 출처/획득 방법/해시/품질 확인 |
| outcome/empirical.py의 빈도·표본 풀링 | EMPIRICALLY_ESTIMATED | 훈련 기간으로만 보정, 별도 검증·최종 검증 기간에서 평가 |
| AI의 새 타석·재추출 위치 | MODEL_SIMULATED | 실제 관측과 별도 레이어, 두 donor ID와 확률·N·모델 ID 보존 |
| 관측 행동의 조건부 확률을 개입 결과에 적용 | UNVERIFIED_ASSUMPTION | 선택 편향·비식별 인과효과를 공개, 한정된 PoC로만 표기 |
| tests/test_evidence.py의 입력 | MOCK_TEST_ONLY | 테스트 전용, 실제 데이터/성과로 저장·발표하지 않음 |

## 이번 환경에서 확인한 외부 접근

공식 `https://baseballsavant.mlb.com/csv-docs`, `/robots.txt`와 구현한 수집 경로의 최초 요청이 환경 프록시에서 `Tunnel connection failed: 403 Forbidden`으로 차단됐다. 공식 사이트의 응답 자체를 수신한 것이 아니므로 사이트 다운/금지/라이선스 상태를 단정하지 않는다.

실제 CSV 확보 수: **0**. 실제 자료의 N·결측률·독립 검증 성적·학습 성과: **미확인**. 다른 저장소의 테스트 CSV를 실데이터 연구 자료로 대신 사용하지 않았다. 공개 pybaseball 수집기 소스는 요청 형식을 검토하는 데만 사용했다.

`data/local/statcast/raw/acquisition_failure.json`과 `outputs/E01/v4-source-status/report-data.json`에 실제 실패 근거를 저장했다. 네트워크 허용 초안에 baseballsavant.mlb.com, www.mlb.com을 추가했다. 초안 저장은 런타임 적용·데이터 획득·모델 검증을 뜻하지 않는다.

## 규칙·단위의 근거

CSV 열 정의의 기준 URL은 https://baseballsavant.mlb.com/csv-docs 이며, 현재 환경에서 페이지 본문을 확인할 수 없었다. 사용한 필드·단위는 제공된 명세와 Statcast 열 이름에 고정하고 계보에 기록한다. 연도를 무분별하게 결합하지 않는다. mph→km/h는 정확한 단위 변환(×1.609344)이다.

스트라이크존 그림의 폭은 홈플레이트 17인치 규칙 도식이고 높이는 해당 표본의 sz_bot/sz_top을 사용한다. 공 반경·심판 판정 모델을 뜻하지 않는다. 규칙 참고: https://www.mlb.com/glossary/rules/strike-zone (이번 환경에서 본문 재확인 불가). 실제 투수가 노린 지점이나 비행 궤적을 도착 위치로부터 만들어내지 않는다.
