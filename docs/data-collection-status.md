# 다중 리그 수집 현황

## 2026-11-12 추가 수집 실적

| 원천 | 실제 확보 | 이번 증가·사용 |
|---|---|---|
| Retrosheet MLB | 2000~2025, 26시즌, 4,925,133플레이·완료 타석 4,705,835 | 2000~2014의 2,937,005플레이 추가. 42,076개 선수·역할·시즌 집계 |
| Kaggle netsong KBO v7 | 1982~2026 타격 10,209행·투구 7,971행, CSV 2개 | 18,180개 원본 선수·역할·시즌 기록 등록. CC BY-NC-SA 4.0 선언. 0타석을 제외한 비교 가능 프로필 18,018개 |
| Kaggle mattop KBO | 1982~2021 팀 타격 323행·팀 투구 323행 | CC0 선언. 독립 비교용 원본으로 보존하며 선수 기준에 중복 합산하지 않음 |
| Kaggle lazyjun01 KBO | 2001~2024 수비 214행, 주루 파일 2개 409행 | CC0 선언. 주루 두 버전의 중복·계수 모순 8건씩을 표시하고 추정 보정·행동 전이에 사용하지 않음 |
| armstjc NPB / SPAIA | CSV 98개, 674,754행, 316,409,470바이트 | 선수 경기 기록 2019~2026 251,464행, 2025 PBP 399,695행, 일정 7,922행, 순위 15,673행 |

NPB 비공식 저장소 revision `5f9108abdaf7db69d3ca976381cf5f59716e75e8`에서 고정 수집했습니다. 선수·경기 ID는 SPAIA 범위이며 타 제공자와 이름으로 연결하지 않습니다. PBP의 `game_type_id`와 일본어 종류명을 함께 확인해 센트럴 공식전·퍼시픽 공식전·교류전만 선택했습니다. 858경기·27,209개 선수 경기 행을 1,002개 선수·역할·시즌 기록으로 집계했고, 그중 842개가 공통 타석 비교 조건을 갖춥니다. 미분류 219,583행과 시범·포스트시즌 등 4,672행은 집계에서 제외하되 원본은 보존했습니다. PBP는 투구·장면 설명 행이며 모두 독립 투구나 학습 가능한 행동이라고 주장하지 않습니다.

표준 저장소에는 출처가 다른 중복 시즌까지 보존한 79,724행이 있습니다. 이는 고유 선수 수가 아닙니다. 비교는 리그·시즌별 제공자를 하나만 선택합니다. KBO는 최신 netsong 배포, NPB는 별도 사용을 선언한 armstjc 배포, MLB는 Retrosheet를 사용하며 이전 제공 자료·공식 NPB 원본은 덮어쓰지 않습니다. 일반 타석을 대조할 뿐 전략 학습 적격으로 자동 승격하지 않습니다.

실파일은 `data/local/community/`, `data/local/collections/`, 버전별 집계는 `data/local/standardized/`에 저장했습니다. 원본·압축·라이선스·설명문·버전·SHA-256은 비공개로 보존하고 Git에는 수집 코드만 넣습니다. NPB 98개 파일은 Git blob SHA와 SHA-256을 모두 대조했습니다. MLB 일부 첫 다운로드는 잘려 ZIP 검사에서 실패했고 새 후보로 다시 확보했습니다. 잘린 원본을 정상 자료로 등록하거나 기존 파일을 덮어쓰지 않았습니다.

비공식 배포처:

- [netsong KBO 선수 CSV](https://www.kaggle.com/datasets/netsong/kbo-player-stats-19822025)
- [mattop KBO 팀 투구](https://www.kaggle.com/datasets/mattop/korean-baseball-pitching-data-1982-2021) · [팀 타격](https://www.kaggle.com/datasets/mattop/baseball-kbo-batting-data-1982-2021)
- [lazyjun01 수비](https://www.kaggle.com/datasets/lazyjun01/kbo-defensive-data2001-2024) · [주루](https://www.kaggle.com/datasets/lazyjun01/kbo-runners-data2001-2024)
- [Joseph Armstrong / Nippon Baseball Data Repository](https://github.com/armstjc/Nippon-Baseball-Data-Repository): MIT 본문과 데이터 출처 표시 추가 조항. SPAIA upstream 재배포권을 독립 확인했다는 뜻은 아닙니다.

This uses data sourced from the Nippon Baseball Data Repository, which can be accessed here:
https://github.com/armstjc/Nippon-Baseball-Data-Repository

## 이전 공식 원본 수집 이력

2026-11-11 실제 확보 파일 기준이다. 수집과 통계 표준화는 학습 모델 검증과 별개다.

| 자료 | 확보 기간 | 실제 단위·분량 | 남은 한계 |
|---|---|---|---|
| MLB / Retrosheet | 2015–2025 | 공식 연도별 원본 11개, 정규시즌 완전 기록 경기의 플레이 1,988,128행 | Statcast 투구 궤적·타구 속도 자료가 아니다. 모델의 예측력은 별도 검증해야 한다. |
| NPB / 공식 팀 통계 | 2015–2025 | 양 리그·타격/투구 44개 표, 팀별 시즌 통계 264행 | 선수·투구 기록으로 바꿔 해석하지 않는다. |
| NPB / 공식 선수 통계 | 2025 | 12구단 타격/투구 24개 표, 타격 725행 + 투구 361행 | 팀별 선수행이며 같은 선수의 역할·팀 간 중복을 합산하지 않는다. 등록 선수 전원 확보를 뜻하지 않는다. |
| KBO / 기존 제공 자료 | 1982–2025 | 기존 사용자 제공 선수 기록 재사용 | 이번 공식 사이트 자동 수집은 진행하지 않았다. 제공 자료의 정의·권리는 별도 관리한다. |

NPB 선수 표에는 적은 타석의 선수도 포함된다. 그러나 공식 고유 선수 ID가 없어, 연도·역할·팀·이름 해시로 **해당 행만 구별하는 ID**를 부여했다. `ROW_SCOPED_NAME_ONLY_NOT_VERIFIED_PERSON_ID`를 함께 기록한다. 같은 이름의 인물을 여러 시즌·팀에서 자동 연결하거나 MLB/KBO 선수와 연결해서는 안 된다. 다른 연도의 선수 표는 형식이 달라 이번 검증 범위에 포함하지 않았다.

각 원본은 `data/local/collections/`에 비공개 권한으로 저장한다. `manifest.json`은 원천 주소·리그·시즌·단위·수집 시각·SHA-256·권리 상태를 보존하고, 구조화된 통계에는 원문 열도 남긴다. 원본과 기존 운영 데이터는 덮어쓰지 않는다. 검증된 스냅샷은 재실행 시 해시를 확인해 재사용한다. 일부 수집이 실패하면 실행 기록에 남기고 종료 코드 1을 반환한다.

파싱 수정본도 별도 후보 폴더에 보존하고 `supersedes`에 이전 manifest 경로·해시를 명시한다. 이번에는 NPB 2025 팀 투구 표 2개의 인라인 이닝 분수 해석을 보완했다. 이전 파일과 원본을 유지하며, 유효한 대체 관계를 확인한 수정본만 선택해 중복 집계를 막는다.

NPB 공식 페이지의 공개 열람과 AI 학습·재배포 허가는 같지 않다. 수집 당시 manifest의 권리 상태는 `PUBLIC_PAGE_REUSE_UNVERIFIED`, 재배포 허용은 거짓이다. 2026-11-12 공식 홈페이지의 2차 이용 금지 고지를 추가 확인해, 현재는 새 NPB 시뮬레이션·학습·기준 환경 선택을 차단한다. 원본 manifest는 보존하며 최신 실행 결정은 [공통 자료 규칙](league-data-contract.md)에 기록한다. Retrosheet 사용에는 출처·저작권 고지를 보존한다.

KBO [robots.txt](https://www.koreabaseball.com/robots.txt)는 사전 승인 없는 자동 수집·크롤링·복제를 금지한다고 명시한다. 따라서 우회하거나 현행 시즌 화면을 과거 연도로 가장해 저장하지 않았다. KBO 자동 수집 기능은 이번 수집기에서 지원하지 않는다.

```bash
# 연도 범위로 MLB 플레이 확보
python scripts/collect_league_seasons.py --leagues MLB --start-year 2000 --end-year 2025

# 공식 NPB 신규 수집은 중단, 별도 비공식 배포본 수집
python scripts/collect_npb_community.py
```

한 번에 최대 두 요청만 진행한다. 공식 자료 배포 여부·권리·실제 열 정의를 확인하며 확장한다. 누락된 피안타 세부 항목이나 투구 위치를 임의로 생성하지 않으며, NPB 투구 이닝의 `.1`·`.2`는 소수가 아니라 각각 아웃 1개·2개로 처리한다. 리그 간 보정되지 않은 기록을 동일한 실력 척도로 취급하지 않는다.
