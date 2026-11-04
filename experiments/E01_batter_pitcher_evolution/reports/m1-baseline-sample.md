> 검증 명령: `python scripts/quickstart.py --seeds 20261104 20261105 20261106 --output outputs/E01/verified`
> 커밋 전 작업 트리에서 생성한 실제 실행 샘플이다. 소스 SHA256으로 사용한 구현을 식별한다. 합성 확률이며 학습 결과가 아니다.

# E01 실행 결과

프로파일: `synthetic_demo` / 보정: `synthetic-v1`
데이터 출처: Hand-authored synthetic probabilities; no real league data

타석 단위의 정책 평가다. 이 실행은 학습을 수행하지 않으며 경기 승패를 측정하지 않는다.

## 대결 요약

| 타자 | 투수 | seed 수 | 타석 | BB% | K% | 안타/타석 | 초구 스윙% |
|---|---|---:|---:|---:|---:|---:|---:|
| random | random | 3 | 3000 | 0.6% | 34.8% | 21.7% | 66.2% |
| random | strike_first | 3 | 3000 | 0.0% | 26.9% | 23.0% | 66.2% |
| random | mixed | 3 | 3000 | 0.1% | 33.4% | 21.3% | 66.2% |
| aggressive | random | 3 | 3000 | 0.0% | 25.0% | 24.0% | 100.0% |
| aggressive | strike_first | 3 | 3000 | 0.0% | 10.2% | 29.1% | 100.0% |
| aggressive | mixed | 3 | 3000 | 0.0% | 20.6% | 26.1% | 100.0% |
| patient | random | 3 | 3000 | 19.8% | 42.9% | 12.1% | 0.0% |
| patient | strike_first | 3 | 3000 | 0.2% | 28.4% | 22.0% | 0.0% |
| patient | mixed | 3 | 3000 | 7.3% | 44.6% | 16.3% | 0.0% |

## 매치업 행렬: 볼넷 비율

| 타자 / 투수 | random | strike_first | mixed |
|---|---:|---:|---:|
| random | 0.6% | 0.0% | 0.1% |
| aggressive | 0.0% | 0.0% | 0.0% |
| patient | 19.8% | 0.2% | 7.3% |

## 매치업 행렬: 삼진 비율

| 타자 / 투수 | random | strike_first | mixed |
|---|---:|---:|---:|
| random | 34.8% | 26.9% | 33.4% |
| aggressive | 25.0% | 10.2% | 20.6% |
| patient | 42.9% | 28.4% | 44.6% |

## 지표·재현성

- BB%, K%, 안타/타석의 분모는 타석 수다. 안타/타석은 타율(안타/타수)과 다르다.
- 초구 스트라이크는 첫 공의 strike/foul 사건이며 인플레이는 포함하지 않는다.
- whiff_per_swing은 스윙 중 strike 사건 비율이다. 스윙이 없으면 null이다.
- results.json에 카운트별 행동·구종 비율, 정책 버전, seed별 결과와 Wilson 95% 구간이 있다.
- Wilson 구간은 각 고정 정책·seed 실행의 이항 표본 요약이다. 모델 편향이나 학습 seed 불확실성을 포함하지 않는다.
- 정책·확률·코드가 같을 때 재현 가능하다. rng-v2는 타석마다 독립 스트림을 시작한다.
- 이 지표는 관찰용이며 학습 보상이 아니다. 최종 연구 목표는 경기 승리다.
- 코드: `b3b6f2a1f303dd5aece526f0325d2724dd7353d4`, SHA256: `47f21390d4bf9ed85266a95d89c6f93e54b2023160168cf9c38636f96dd67af3`
