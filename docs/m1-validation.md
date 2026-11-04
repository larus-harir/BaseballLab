# M1 실행 검증

## 실행 환경과 명령

Python 3.12.14 / pytest 8.3.5 / Linux CPU에서 검증했다.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/quickstart.py --mode baseline
python scripts/quickstart.py --mode baseline --seeds 20261104 20261105 20261106 --output outputs/E01/verified
```

현재 테스트 **69 passed**. 기본 실행은 9개 대결·9,000타석, 3개 seed 반복은 27개 대결·27,000타석이다. 모듈 실행 `python -m baseball_lab --list`, 설치된 `baseball-lab` 명령, E01 자체 run.py를 다른 작업 디렉터리에서도 실행했다.

## 결과 파일 검증

3개 seed 실행에서 투구 로그 **77,522행**, 타석 종료 **27,000개**를 확인했다. 전체 pitches.csv를 순회해 매치별 사건·최종 결과 수가 JSON의 집계와 일치함을 확인했다. 동일 seed 반복 실행의 matches 데이터가 같았다.

예: 인내 타자 vs 랜덤 투수는 3,000타석의 볼넷 비율 19.8%, 삼진 비율 42.9%, 초구 스윙률 0.0%다. 이는 합성 모델에 대한 고정 정책의 결과다. 학습 전략의 발견, 실제 야구의 우열 또는 경기 승률을 의미하지 않는다.

[실행 리포트 샘플](../experiments/E01_batter_pitcher_evolution/reports/m1-baseline-sample.md)과 [투구 로그 샘플](../experiments/E01_batter_pitcher_evolution/reports/pitch-trace-sample.csv)을 저장했다. 전체 출력은 outputs/ 아래에 있으며 Git에서는 제외한다.

## 검증 범위

- 볼넷·삼진·파울·인플레이 종료와 불법 행동·잘못된 카운트 거부.
- 모든 합법 행동의 확률 유효성, 능력 경계값 및 능력 변경에 따른 결과 변화.
- 정책 관측에 현재 투구·결과가 없음, 결과 모델에는 상태·능력 전달.
- 신규 정책·다른 프로파일·새 실험 ID가 같은 엔진/평가/기록을 재사용.
- 실제 대결 경로에서 정책 스키마 불일치 거부.
- 설정 오류를 실행 전에 검사, seed 반복·카운트별 집계·Wilson 구간·CSV 결과 재구성.
- 시뮬레이션 실패 시 이전 결과 유지, 집계 전용 실행에서 오래된 trace 정리.
- Git 미설치 상황의 기록 처리, CLI의 외부 작업 디렉터리 실행·잘못된 입력 종료 코드.

기존 커밋의 RNG는 연속 스트림이고 현재는 타석별 독립 스트림이다. 결과 차이는 results.json의 rng_version=`per-pa-stream-v2`와 코드 SHA256으로 구분한다.

Python 3.11–3.13 / Ubuntu·Windows용 GitHub Actions를 추가했다. 여기서 실제 실행한 로컬 환경과 CI 설정을 구분하며, 원격 CI 통과를 미리 주장하지 않는다. 실제 리그 데이터 수집·보정, 전체 경기, RL 학습은 개발 단계에 구현 상태를 기록했다.
