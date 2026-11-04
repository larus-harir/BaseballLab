# Baseball AI Lab — 실제 기록 기반 시뮬레이션·시각화 구현 명세 v1

**적용 범위:** 부모 플랫폼 전체, 우선 구현 대상 E01.
**문서 우선순위:** `Baseball_AI_Lab_PROJECT_VISION_v4.md` → 본 문서 → 기존 Master Handoff / Codex 프롬프트. 충돌 시 v4가 우선한다.

## 1. 목표 화면은 '야구 게임 화면'이 아니라 '전략 진화 관찰실'

유저는 경기 결과뿐 아니라 **한 공의 선택 → 타자의 대응 → 결과 → AI 전략 업데이트 → 다른 상대와의 재대결 → 인간 야구와의 차이**를 눈으로 따라갈 수 있어야 한다. 복잡한 3D 게임 엔진보다 검증 가능한 2D 정보 시각화에 우선순위를 둔다.

### 뷰 A: Pitch / At-bat Replay — 1구 단위 리플레이 (우선)

- 상단: 리그, 시즌/규칙 버전, 이닝, 점수, 아웃, 주자, 카운트, AI 버전, 실험 ID.
- 좌측: 포수 시점 스트라이크존 2D 도식, 선택된 투구의 실제/시뮬레이션 도착 위치·구종·구속 (지원 항목만), 이전 투구 궤적 히스토리.
- 우측: 투수에게 보인 정보·행동 선택·정책 확률, 타자에게 보인 정보·행동 선택·정책 확률; 결과는 결정 이후 별도로 표시.
- 하단: 공 단위 이벤트 타임라인, 일시정지, 다음 투구, 이전 투구, 1배속/4배속/즉시 재생, 체크포인트·시드 변경.
- 제공 가능하면 타구 방향과 수비 위치를 표시하되, 데이터 또는 검증된 결과 모델이 없다면 해당 시각 요소를 비활성화한다.
- 각 이벤트에는 source status (`REAL_OBSERVED` / `MODEL_SIMULATED`) 라벨이 있고, 모든 위치·확률에 마우스오버 또는 세부정보로 출처/모델 근거가 드러나야 한다.

### 뷰 B: Strategy Evolution — 학습 진화 (필수)

- X축: 훈련 스텝, 누적 대결 수, 체크포인트 (구분을 유지). Y축: 행동 빈도·실제 평가 성적.
- 타자: 초구 스윙, 카운트별 테이크, 컨택/파워 스윙(지원 시), 선택 행동 확률 분포.
- 투수: 구종 분포, 스트라이크존 공략, 볼카운트별 선택, 코스 분포.
- 겹쳐보기: 타자 A의 변화와 투수 B의 대응 변화를 같은 타임라인에 표시하되 인과관계라고 단정하지 말 것.
- 체크포인트 비교: V1/V2/V3, 고정 baseline, 과거 상대, 상대 풀. 서로 최신 모델끼리의 50% 승률만으로 발전을 평가하지 말 것.
- 무효 샘플이나 표본 적음/불확실성이 큰 구간에 경고 표시. N, 평가 게임 수, 평가 규칙, seed와 데이터 버전을 표기.

### 뷰 C: Reality Check — 실제 야구 대비 검증 (필수)

- 실제 Statcast에서 관측된 `구종×카운트×코스×결과` 등 검증 가능한 분포와 모델 예측/시뮬레이션 분포를 나란히 표시.
- 예: 관측 구종별 비율, 카운트별 볼/스트라이크/인플레이 결과, 스윙·헛스윙 비율(측정 가능한 정의와 분모 명시), 바깥쪽/안쪽 코스, 타구속도/발사각 등 (확보 데이터에 한함).
- 모델의 편차를 절대 오차, 조건별 빈도 차이 등 적절한 지표로 표시. 시뮬레이션 '개선'이 단순히 환경의 결함인지 검사한다.
- 역사 비교 시 동일한 기록 정의·룰·표본 구간을 맞춘다. 다른 데이터 시대는 '비교 제한' 표시.

### 뷰 D: League / Experiment Compare — 장기 확장

- E01 / E02 / E03 전환, MLB/KBO/연대 선택, 동일 조건 비교 모드와 해당 리그 규칙·선수 능력을 포함한 환경 비교 모드를 분리.
- 같은 스키마/화면 컴포넌트를 재사용하며 KBO에 없는 투구 수준 특성을 MLB에서 추정해 끼워 넣는 방식으로 '실제 KBO'를 꾸미지 않는다.
- 지원하지 않는 지표에는 N/A 사유, 데이터 가용 연도, 출처와 비교 가능 범위를 보인다.

## 2. 실제 근거가 필요한 데이터 항목과 금지되는 추론

| 대상 | 활용 가능한 실제 근거 | 주의 / 불허 |
|---|---|---|
| 구종/구속/회전/위치 | Statcast pitch_type, release_speed, release_spin, plate_x/z 등 | 연도별 스키마·센서 정의 다름. 의도한 코스를 실제 도착 코스로 간주 금지 |
| 카운트/상황 | balls/strikes, outs_when_up, 주자/이닝/점수 | 미래 결과 및 사후 지표를 투구 전 관측으로 넣지 말 것 |
| 타구 | launch_speed, launch_angle, hc_x/y, bb_type 등 | 모든 공에 관측되는 것이 아님. 임의 궤적·수비수 모션 금지 |
| 실제 결과 | description, events, Retrosheet event | 관측된 선택의 결과이지 '선택하지 않은 행동의 결과'는 아님 |
| 시대별 비교 | Retrosheet 이벤트/연도별 데이터, 룰 메타데이터 | 과거 전 시즌에 현대와 같은 투구 센서 데이터가 존재한다고 가정 금지 |
| KBO | KBO 공식 기록실에서 접근 가능한 시즌·선수·팀 지표 | 동급 세부 투구 데이터가 있는지 확인하기 전에는 E02 상세 학습 불가 |

**공식/대표 출처 링크**
- MLB Baseball Savant CSV schema: https://baseballsavant.mlb.com/csv-docs
- Retrosheet event files: https://www.retrosheet.org/game.htm
- Retrosheet parsed play-by-play: https://www.retrosheet.org/downloads/plays.html
- KBO 공식 타자 기록실: https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx
- KBO 공식 투수 기록실: https://www.koreabaseball.com/Record/Player/PitcherBasic/Basic1.aspx

**주의:** 위 사이트에 데이터가 존재한다는 것이 모든 형태의 자동 수집·재배포 권한을 의미하지 않는다. 각 출처의 사용조건/속도 제한을 확인한다.

## 3. 데이터·실험 계약 및 UI에서의 표시 방식

각 기록/실험 이벤트에 다음 구조가 필요하다. 구체 형식은 Python dataclass/JSON/SQLite 등 현재 코드에 맞춰 결정.

```
DataLineage: source_name, source_url, season_range, acquired_at,
             raw_file_checksum, schema_version, filter_summary,
             raw_rows, used_rows, missingness_report, licensing_notes

EnvironmentVersion: ruleset_id, league, season_context,
                    calibration_id, model_version, action_space_version,
                    unsupported_features, assumptions

ExperimentRun: run_id, child_experiment_id, seed,
               dataset_version, environment_version, policy_checkpoint_ids,
               training_steps, eval_protocol, started_at, completed_at

PitchEvent: event_id, run_id, game_id, inning, score, outs, bases,
            balls, strikes, observed_state_batter, observed_state_pitcher,
            pitcher_action, batter_action, sampled_result, reward,
            source_status, reference_record_ids, probabilities_used

PolicySnapshot: policy_id, run_id, checkpoint_step, matchup_pool,
                action_distribution_summary, evaluation_n, evaluation_metrics
```

어떤 화면이든 숫자·플레이·차트 점을 선택하면 `run_id`/`event_id`와 원천 또는 모델 버전으로 역추적 가능해야 한다. 새 필드를 만들 때 실데이터에서 실제 확인할 수 있는지부터 검토한다.

### 데이터 상태 표기 (공통)

- `REAL_OBSERVED`: 실제 경기에서 측정/기록된 데이터.
- `EMPIRICALLY_ESTIMATED`: 실제 자료에 맞춰 추정한 파라미터/통계 모델.
- `MODEL_SIMULATED`: 해당 모델로 AI가 수행한 가상 경기 기록.
- `UNVERIFIED_ASSUMPTION`: 아직 실제 데이터로 검증할 수 없는 가정.
- `MOCK_TEST_ONLY`: UI/단위테스트용 가짜 값. 연구 화면·분석·리포트에 섞지 말 것.

원천 관측값, 통계 추정값, 모델 생성값은 다른 라벨과 시각적 범례를 사용한다. 빈 화면을 채우는 데 fake 표본 사용 금지.

## 4. 구현 순서 — 일반 노트북 / Colab 고려

**0단계 (데이터 감사):** Statcast의 실제 제한된 기간 CSV 확보, 필드 검증, 출처 및 단위 저장, 샘플 수·결측 통계. 사용조건 준수. 미확보 시 수집 방해 원인을 출력하고 연구 실험 중단.

**1단계 (환경 보정):** 실제 관측에서 얻을 수 있는 최소 카운트/구종/코스/결과 확률 추정. 데이터 희소 구간은 과도하게 세분화하지 않고 계층적/풀링 접근과 불확실성 보고. 사전에 정한 평가 기간에서 검증.

**2단계 (최소 학습):** 관측 가능한 상태/행동만 사용하는 타자·투수 학습, 체크포인트 및 로그. 반사실 샘플링은 반드시 `MODEL_SIMULATED`로 표기; 관측되지 않은 행동의 결과가 검증되지 않았다면 지원 범위 축소.

**3단계 (최소 UI):** 실제 실행 로그로 리플레이(스트라이크존 + 이벤트 + 선택 정책), 전략 변화 차트, 모델/실제 비교 한 화면씩. 정밀 애니메이션 없이 구현 가능.

**4단계 (확장):** 타구 시각화, 주자/이닝/승패, 현실적 피로·시프트·번트 등 데이터 검증이 되는 범위로 확대. E02는 KBO 데이터 가용성 감사 후 추진.

## 5. 완료 조건 / 실패 처리

- [ ] 실데이터 원천, 기간, 조건, 스키마, 해시, 결측 보고서가 존재한다.
- [ ] 시뮬레이션 결과를 만든 확률/물리/규칙 모델이 구체적 데이터와 연결되어 있다.
- [ ] 별도 보류 데이터에서 분포/예측 적합도와 실패 구간을 점검했다.
- [ ] AI 양쪽의 정책이 실제 업데이트된다. 고정 정책/난수 게임을 AI 학습이라고 주장하지 않는다.
- [ ] 리플레이의 모든 표시 항목과 전략 그래프가 실행 로그 및 출처로 추적된다.
- [ ] 실제 경기와 시뮬레이션 기록에 구분 태그가 있다.
- [ ] 표본 부족, 결측, 미지원 피처, 미검증 인과효과는 숨기지 않고 표시한다.
- [ ] 유의미한 결과가 없으면 `결과 미확인`이라고 기록한다.
- [ ] 실데이터를 못 구했다면 '연구 완료' 대신 '데이터 확보 필요' 상태로 보고한다.

## 6. Codex가 작업 종료 시 알려줄 보고 양식

1. **연구 질문:** 이번에 테스트하는 구체적 전략 가설.
2. **근거 데이터:** 사용한 공식 출처, 기간, N, 결측, 단위, 보류 데이터 구간.
3. **모델 구분:** 관측/추정/시뮬레이션/미검증 가정/테스트용 mock.
4. **실제 구현 화면:** 실제 실행 로그 기반 리플레이, 전략 변화 그래프, 현실 검증 그래프의 경로.
5. **검증 결과:** 평가 규칙, 기준선, 상대, seed, 모델 적합도, 실패/한계.
6. **미지원 항목:** 데이터 부재 때문에 보류한 공종/수비/주루/타구 궤적 등.
7. **다음 단계:** 어떤 자료가 확보되면 어떤 행동 공간을 확장할지.

**합격 기준:** 눈에 띄는 화면보다 **연구의 증거를 화면으로 볼 수 있는 것**이 우선이다.
