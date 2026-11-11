# 현재 자료 계약과 지원 시즌 (2026-11-11)

MLB 2023/2024 선수 대결·Match 원본, KBO 1982~2025 과제는 `DatasetCatalog`에서 공통 관리합니다. [실제 제공원·조건·원본 해시](data-provider-review.md), [현재 독립 검증](model-independent-validation.md), [통합 결과](incremental-redesign-validation.md)를 따릅니다. 기존 카탈로그와 원본은 이동/재생성하지 않았습니다.

아래는 각 원천을 도입한 시점의 이력입니다. 이전의 ‘2024만 지원/새 준비 버튼’ 안내는 현재 자동 준비·2023 확장으로 대체했습니다.

---

# 실제 자료·사용조건·가용성

## MLB Statcast

- 원천/열 정의: https://baseballsavant.mlb.com/csv-docs
- 공식 검색·CSV 내보내기: https://baseballsavant.mlb.com/statcast_search
- 이용 조건 참고: https://www.mlb.com/official-information/terms-of-use
- 공개 수집기 요청 형식 참고: https://github.com/jldbc/pybaseball/blob/master/pybaseball/statcast.py

초기 요청은 프록시 403이었지만, 게시된 환경에서 공식 설명·robots.txt·MLB 약관·지표 정의 페이지를 200 응답으로 확인했다. 약관에 자동 스크립트 수집 제한이 있어 기본은 공식 CSV 내보내기 후 웹 업로드이며, 원본 CSV와 실제 학습 성과는 아직 없다. 별도 허용 근거를 명시한 자동 수집기만 robots.txt를 확인하고 금지/확인 실패 시 중단한다. 공개 접근이 재배포 허가를 뜻하지 않으므로 원본은 Git에 넣지 않는다. 목적별 이용 가능 여부를 확인하고 그 내용을 usage-note에 기록한다. 코드가 법적 사용 허가를 발급하거나 증명하지 않는다.

직접 내보내기 자료는 공식 HTTPS 검색 URL·획득 시각(시간대 포함)·해시·사용조건 메모와 함께 가져올 수 있다. source acquisition_method는 user_attested_export이며, 자동 공식 획득과 구분한다. 같은 기간의 여러 일별 CSV를 --csv로 반복 지정할 수 있다.

처음에는 2024 정규시즌 6일을 일별 수집한다. 연도별 기록 정의가 달라질 수 있어 현재 감사기는 여러 연도의 혼합을 거부한다. 결측 센서 값은 None으로 보존하며 임의 평균·구속·좌표를 채우지 않는다. 출시된 열 정의의 재검토와 연도 간 비교는 별도 어댑터 버전으로 다룬다.

## Retrosheet

현재 E01-R1의 실제 원천이다. 2026-11-04 UTC에 공식 https://www.retrosheet.org/downloads/plays.html 과 공식 2024년 ZIP https://www.retrosheet.org/downloads/plays/2024plays.zip 에 접근해 배포·열 정의·고지를 확인했다. 직전 프록시 CONNECT 403은 이 공식 경로에서 해소됐으며, 이를 모든 MLB 도메인의 수집 권한이나 접속 보장으로 확대하지 않는다.

공식 NOTICES는 “Recipients of Retrosheet data are free to make any desired use of the information”라고 설명하고 지정한 저작권 고지의 명시를 요구한다. README·각 결과 보고서에 원문을 표시한다. 정확성을 보증하지 않으며 향후 수정 가능하다는 공식 설명도 함께 고려한다.

- 확인한 ZIP SHA256: `a3e8c08876ddf70e1ffb0b20486c2873cf4aae19e0acc8002096e9056107615b`.
- 공식 파싱 CSV를 그대로 보관하며, `gametype=regular`, `pbp=full`만 사용한다. 포스트시즌·올스타전 등 제외 수를 기록한다.
- 아웃·주자·득점·PA 종료·번트 관측·고의볼넷과 원문 이벤트·투구 결과 문자열을 사용한다. 구종·좌표·구속·의도는 생성하지 않는다.
- 원본·이용 고지·체크섬은 `data/local/retrosheet/official-2024`에 보존한다. 공식 수정 배포의 해시가 달라지면 재검토 전 멈춘다.
- 초기 조사에서는 Chadwick의 Retrosheet official 브랜치 미러와 외부 파서도 확인했다. 최종 기본 경로는 **공식 파싱 CSV 직접 배포**이며 Git·C 컴파일러·외부 실행 파일 설치를 요구하지 않는다.

The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at 20 Sunset Rd., Newark, DE 19711.

## KBO / E02

공식 타자/투수 기록실:

- https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx
- https://www.koreabaseball.com/Record/Player/PitcherBasic/Basic1.aspx

이번 작업에서 해당 자료의 자동 수집·재이용 조건이나 세부 피치 데이터의 가용성을 확인하지 않았다. E02는 미구현이며, Statcast 수준의 좌표·센서·정책 의도를 확보했다고 가정하지 않는다. MLB 데이터로 결측을 채워 실제 KBO 학습 AI로 표시하지 않는다.

## 추가 확인: 2023년 공식 배포

공식 `https://www.retrosheet.org/downloads/plays/2023plays.zip`의 SHA256 `0129befd7944f60a858e5fdc265a44ed20afaa568679b37fca1083e3c083b20e`를 개별 등록했습니다. 2,430경기·184,506개 턴을 정규화하고 2024년 고정 정책의 외부 시즌 평가를 실제 수행했습니다. 원본의 행정용 NP 567행과 이닝 종료 후 NP 1행은 실제 플레이가 아니므로 원천 ID·사유를 보존해 제외했습니다. 아웃/주자를 임의 보정하지 않았습니다. 기존 2024년 원천·저장 정책은 유지했습니다.

배포별 메타데이터는 `data.retrosheet_releases`에 있고, 자동 해시 변경이나 미검토 연도 추측은 하지 않습니다. 다른 시즌 성능은 [실제 검증](match/validation.md)을 참고하세요. 같은 시즌을 외부 평가라고 부르거나, 미검증 KBO 기록을 섞지 않습니다.

## 2026-11-09 통계 대결 카탈로그

**BaseballLab:** 기존 공식 공급원에서 받은 `https://www.retrosheet.org/downloads/plays/2024plays.zip`을 재사용합니다. 실제 사용 URL·해시는 카탈로그 source와 [예측 검사 기록](results/mlb-matchup-predictive-validation.json)에 보존합니다. 이름은 공식 `https://www.retrosheet.org/events/2024eve.zip`의 `.ROS`에서 선수 ID로 연결합니다(고정 SHA-256 `5dfd9ed678c9c619f6a216322922c99234c067d0ec15b12790546f620ced2fa4`). 같은 시즌의 정규·완료 기록 중 `pa=1`만 사용하고 `(gid,pn)` 중복과 K/BB/HBP/단타/2루타/3루타/HR의 중복을 거부합니다. 나머지는 기타 타석 결과이며 모두 아웃으로 단정하지 않습니다. 실제 `ab/sf/sh`는 별도 집계합니다. 현재 182,449타석, 타자/투수 역할별 1,506 프로필입니다.

프로필의 시즌 전체 탐색과 기간 분리 예측 검사는 구분합니다. 예측 검사의 분모·선수 기록은 최초 구간에서만 계산하고, 중단 경기는 실제 CSV `date`의 마지막 타석 날짜로 경기 전체를 배정합니다. 경기 ID 원래 날짜만 써서 미래 재개 타석을 과거에 섞지 않습니다. 구종·구속·코스·미관측 의도를 채워 넣지 않습니다.

**EraMatch:** 제공된 `code.zip`의 SHA-256은 `57ab8411a07b901206b0af798d9f55a00cab79ea1d61adac492e86571b2a1058`입니다. 검토한 정확한 3개 멤버만 크기를 제한해 읽고, Python 원본은 앱에서 실행하지 않습니다. CP949 타자 9,731행·투수 7,727행에서 ID/시즌/역할로 17,116 프로필을 구성합니다. 중복 팀/합계/이름 모순 4그룹은 차단합니다. 서로 다른 팀 행 339그룹은 개선 후보에서 합산하는 가정을 명시하며, 원본 방식은 조건을 만족한 첫 행을 유지합니다.

KBO 자료는 `LEGACY_UNVERIFIED`입니다. 원본 Kaggle URL·버전·재배포 권한을 독립 확인하지 못했습니다. HP→사구 후보 대응 및 BB/IB의 포함 관계도 미확인입니다. 일부 과거 투수의 피2루타/피3루타가 비어 있으므로 개선 후보를 막습니다. KBO 원본 ZIP/CSV/Python/PDF를 Git에 싣지 않으며, 새 PC에는 사용자가 보관한 원본 ZIP의 최초 연결이 필요합니다.

두 프로그램은 `data/local/catalog/`를 공유하며, 각 실행에 자료 ID·원본 해시·모델·코드 지문·재현 번호·반복 횟수를 저장합니다. MLB 선수 카탈로그는 원본 배포 ZIP을 사본으로 보존하므로 기존 R1 캐시를 별도로 정리해도 카탈로그 원본 검사가 유지됩니다. 네트워크 재다운로드 공급원을 따로 만들지 않습니다.

지표 정의/근거는 [SABR 다항 Log5](https://sabr.org/journal/article/matchup-probabilities-in-major-league-baseball/), [MLB BABIP](https://www.mlb.com/glossary/advanced-stats/babip), [MLB FIP](https://www.mlb.com/glossary/advanced-stats/fielding-independent-pitching)를 대조했습니다. FIP를 계산에 새로 넣거나 ‘운 제거·진짜 실력 추출’을 입증했다고 주장하지 않습니다. 다른 지표·리그·독립 시즌 검증은 후속 카탈로그 확장으로 남깁니다.
