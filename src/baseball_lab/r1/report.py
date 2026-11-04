"""Standalone Korean view of measured checkpoints, held-out errors and real replay logs."""
import json
from pathlib import Path
from statistics import mean


def report(output, result):
    output = Path(output)
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    template = Path(__file__).with_name('report.html').read_text(encoding='utf-8')
    (output/'report.html').write_text(template.replace('__RESEARCH__', payload), encoding='utf-8')
    lines = ['# E01-R1 · 실제 기록 기반 득점 상황 경쟁 학습', '',
             f"상태: {result['status']} / 실행 ID: `{result['run_id']}`", '',
             '목표는 세 아웃 전에 한 점 이상 득점하기 / 이를 막기입니다. 전체 경기 승률이 아닙니다.', '',
             '타격 측: 일반 타석 / 번트 시도가 포함된 타석. 투구 측: 정상 승부 / 고의볼넷.',
             '선수의 실제 스윙·구종·코스를 재현하는 모델은 아닙니다. 번트 관측의 선택 편향을 제거하지 못했습니다.', '',
             f"실제 자료: {result['dataset']['provider']} / 원본 {result['dataset']['raw_event_rows']:,}행 / {result['dataset']['games']:,}경기", '',
             '| 구간 | 날짜 | 실제 턴 기록 | 경기 수 |', '|---|---|---:|---:|']
    for name, part in result['model']['split'].items():
        lines.append(f"| {name} | {' ~ '.join(part['dates'])} | {part['n']:,} | {part['games']:,} |")
    lines += ['', f"독립 기간 전이 분포 차이(가중 TV): {result['model']['test']['weighted_total_variation']:.4f}",
              '이 값은 예측 오차의 기술 통계이며 현실성·인과 검증의 합격증이 아닙니다.', '',
              '| seed | 두 AI 가중치 변경 | 초기 타격 측 득점률 | 학습 후 타격 측 득점률 | 초기 투구 측 실점률 | 학습 후 투구 측 실점률 |',
              '|---|---|---:|---:|---:|---:|']
    for run in result['seeds']:
        if 'test_evaluation' not in run:continue
        def rate(which, role):
            return next(r['scoring_rate'] for r in run[which] if r['learner_role']==role and r['opponent']=='fixed')
        lines.append(f"| {run['seed']} | {run['both_parameters_changed']} | {rate('initial_test_evaluation','batter'):.3f} | {rate('test_evaluation','batter'):.3f} | {rate('initial_test_evaluation','pitcher'):.3f} | {rate('test_evaluation','pitcher'):.3f} |")
    lines += ['', '평가: 나중 기간으로 별도 적합한 환경, 모든 아웃·주자 상태를 같은 비중으로 시작. 실제 경기 발생 빈도와 다릅니다.',
              '구간은 대결 난수의 오차만 반영하며, 데이터·선택 편향·환경 불확실성은 포함하지 않습니다.', '',
              '고정/초기/과거/사람의 관측 빈도 상대 및 체크포인트 교차대결은 report.html에서 확인하세요.', '',
              '원본·데이터/환경/코드 해시·설정·체크포인트·리플레이는 같은 폴더 및 data/local/retrosheet에 보관됩니다.', '',
              '## 아직 확인하지 못한 것', '', *['- '+a for a in result['assumptions']], '', result['dataset']['credit']]
    (output/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
