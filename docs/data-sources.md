# 실제 자료·사용조건·가용성

## MLB Statcast

- 원천/열 정의: https://baseballsavant.mlb.com/csv-docs
- 공식 검색·CSV 내보내기: https://baseballsavant.mlb.com/statcast_search
- 이용 조건 참고: https://www.mlb.com/official-information/terms-of-use
- 공개 수집기 요청 형식 참고: https://github.com/jldbc/pybaseball/blob/master/pybaseball/statcast.py

현재 클라우드의 공식 도메인 요청은 프록시 단계 403이며 페이지 본문·원본 CSV를 확보하지 못했다. 사용조건이나 사이트 상태를 확인했다고 주장하지 않는다. 자동 수집기는 robots.txt를 확인하고 금지/확인 실패 시 중단한다. 공개 접근이 재배포 허가를 뜻하지 않으므로 원본은 Git에 넣지 않는다. 목적별 이용 가능 여부를 확인하고 그 내용을 usage-note에 기록한다. 코드가 법적 사용 허가를 발급하거나 증명하지 않는다.

직접 내보내기 자료는 공식 HTTPS 검색 URL·획득 시각(시간대 포함)·해시·사용조건 메모와 함께 가져올 수 있다. source acquisition_method는 user_attested_export이며, 자동 공식 획득과 구분한다. 같은 기간의 여러 일별 CSV를 --csv로 반복 지정할 수 있다.

처음에는 2024 정규시즌 6일을 일별 수집한다. 연도별 기록 정의가 달라질 수 있어 현재 감사기는 여러 연도의 혼합을 거부한다. 결측 센서 값은 None으로 보존하며 임의 평균·구속·좌표를 채우지 않는다. 출시된 열 정의의 재검토와 연도 간 비교는 별도 어댑터 버전으로 다룬다.

## Retrosheet

https://www.retrosheet.org/game.htm 및 https://www.retrosheet.org/downloads/plays.html 은 후속 주루/이닝 전이·역사 비교의 후보다. 이번 작업에서 수집·이용 조건·시대별 대응을 검증하지 않았다. 현재 모델에 실제 전이 근거로 연결하지 않는다.

## KBO / E02

공식 타자/투수 기록실:

- https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx
- https://www.koreabaseball.com/Record/Player/PitcherBasic/Basic1.aspx

이번 작업에서 해당 자료의 자동 수집·재이용 조건이나 세부 피치 데이터의 가용성을 확인하지 않았다. E02는 미구현이며, Statcast 수준의 좌표·센서·정책 의도를 확보했다고 가정하지 않는다. MLB 데이터로 결측을 채워 실제 KBO 학습 AI로 표시하지 않는다.
