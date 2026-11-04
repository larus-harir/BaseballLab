# M1 실행 검증

Python 3.12.14, pytest 8.3.5에서 실행했다.

```bash
/workspace/venvs/baseball-lab/bin/python -m pip install -e '.[dev]'
/workspace/venvs/baseball-lab/bin/python -m pytest -q
/workspace/venvs/baseball-lab/bin/python scripts/quickstart.py
```

테스트 **39 passed**. 9조합 × 1,000타석 = 9,000타석 종료를 확인했다. 동일 seed 재실행의 matches 결과가 같았다. 규칙 경계, 2스트라이크 파울, 인플레이 종료, 모든 합법 행동의 확률 유효성, 불법 행동 거부, 공개 관측, 프로파일·규칙 주입, 스키마 불일치 거부, safety limit, 파일 기록을 검증했다.

샘플: seed 20261104, 인내 타자 vs 랜덤 투수 1,000타석에서 볼넷 207, 삼진 423, 인플레이 아웃 243, 단타 88, 2루타 27, 3루타 3, 홈런 9. 초구 스윙률은 0.0이다. 이는 고정 정책과 합성 확률의 출력이며 학습 성과나 인간 야구 전략의 증거가 아니다.

전체 JSON/CSV는 outputs/E01/에 있으며 Git에서는 제외한다. 추적 기록은 프로파일·규칙·seed·정책·Python·코드 SHA256·Git revision/dirty 여부를 포함한다. 초기 저장소는 커밋 없는 상태여서 revision은 unborn이고 소스 해시를 병기한다.

실제 데이터 수집, 전체 경기, 경기 승률, RL, 체크포인트 로딩, KBO 접근 조건 검토는 실행하지 않았다. 설치 시 기본 실행 샌드박스가 네트워크를 차단했지만 승인된 실행 경로와 기존 프록시로 패키지 설치를 완료했고 TLS 검증을 유지했다.
