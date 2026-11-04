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
