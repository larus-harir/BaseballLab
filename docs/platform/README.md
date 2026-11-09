# BaseballLab 프로그램과 공통 기반

2026-11-09 [역할 개정](../specs/BaseballLab_Three_Project_Redefinition_Codex.md)을 적용합니다. BaseballLab은 **통계 타자·투수 대결을 직접 실행하는 프로그램**입니다. 공통 엔진도 제공하지만 공통 기반만 제공하는 부모가 아닙니다.

| 웹 경로 | 실행 기능 | 소유 |
|---|---|---|
| `/`, `/lab` | 세 프로젝트 선택 | 공통 홈 |
| `/baseball` | MLB 실제 선수·시즌, 다항 Log5, 반복 타석, 계산 설명 | BaseballLab |
| `/eramatch` | KBO 과제 검색·시대 보정·원본/개선 후보·25타석 | EraMatch |
| `/match` | AI 경쟁 학습 연구 선택 | Match |
| `/match/team` | 기존 한 점 득점 AI 학습·선택/성과 변화 | Match R1 |
| `/match/at-bat` | 기존 투구 연구 연결·준비 상태 | Match, 연구 검증 미완성 |
| `/simulation` | 기존 실제/가상 한 점 장면 관찰 | R1 관찰 호환 경로 |
| `/lab/data` | 원본·선수 카탈로그·결과 용량, 무결성 검사, 확인 후 삭제 | 공통 자료 관리 |

## 모듈 책임

- `matchup/catalog.py`: 고유 선수 ID+역할+리그+시즌, 팀 분할/중복, 결측, 과제 원본 검증. 원본 코드는 실행하지 않고 기록만 파싱한다.
- `matchup/mlb.py`: 기존 공식 공급원을 재사용한 MLB 실제 타석 집계·공식 이름·기간 분리 예측 검사.
- `matchup/models.py`: 공유 이항/다항 Log5, 평균 회귀, 과제 원본 방식, 몬테카를로. EraMatch 전용 계산식의 복제 없음.
- `matchup/service.py`, `matchup/web.py`, `web/matchup.html`: 선택 프로필→계산→저장→재열기, 결과와 맥락형 설명.
- `experiments/match/`: 목표·보상·신경망 정책·경쟁 학습·상대별 평가·해석. 인간 야구의 역사/현대 비교도 이 영역이며 미완성 상태를 밝힌다.
- `experiments/eramatch/`: 시대 대결 프로그램의 책임 선언. 엔진과 자료를 복제하지 않는다.
- `r1.data/provider`, `data.retrosheet_releases`, `simulation.scoring`: 기존 실제 자료 어댑터와 독립 장면 관찰을 보존한다.
- `web/server.py`, `web/storage.py`: 로컬 서버·토큰·고정 요청·경로 제한·비공개 보관·명시적 삭제 확인을 공통 제공한다.

의존성은 UI/연구 → 공통 자료·모델 방향이다. 통계 모델은 Match 학습기를 import하지 않는다. 보류 기간의 예측 성능이 좋아도 행동 변경의 반사실 결과가 검증됐다는 뜻은 아니다. 따라서 새 Log5 모델을 기존 Match 환경에 자동 삽입하지 않았다.

[실행·검증·제한](../three-project-validation.md) · [보안](../security-audit.md)
