"""v4 offline evidence viewer. Empty panels stay empty; no synthetic filler."""
import json
from pathlib import Path

from baseball_lab.data.lineage import write_json


def write_report(output, run=None, dataset=None, model=None, replays=None, *, failure=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    observed=[]
    if dataset:
        # Small display sample only. Quality/validation statistics use their full partitions.
        heldout=set(model['split']['test']['record_ids']) if model else set()
        observed=[r for r in dataset['records'] if not heldout or r['record_id'] in heldout][:300]
    payload={'run':run,'manifest':dataset['manifest'] if dataset else None,
             'observed':observed,'model':{k:v for k,v in model.items() if k!='fit_records'} if model else None,
             'replays':replays or [],'failure':failure,
             'status':'DATA_REQUIRED' if not dataset else 'MODEL_VALIDATION_REQUIRED' if not model else
                       'RESEARCH_VALIDATION_FAILED' if not model['validation']['research_ready'] and model['source_status']!='MOCK_TEST_ONLY' else
                       'MOCK_TEST_ONLY' if model['source_status']=='MOCK_TEST_ONLY' else 'LIMITED_OBSERVATIONAL_POC'}
    write_json(output/'report-data.json',payload)
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    template=Path(__file__).with_name('evidence_view.html').read_text(encoding='utf-8')
    temporary=output/'report.html.tmp'
    temporary.write_text(template.replace('__REPORT_DATA__',encoded),encoding='utf-8')
    temporary.replace(output/'report.html')
    lines=['# E01 · 실제 근거 기반 관찰실','',f"상태: {payload['status']}",'']
    if failure: lines.extend(['데이터 확보 필요. 연구 학습을 실행하지 않았습니다.',str(failure),''])
    if dataset:
        m=dataset['manifest'];lines.extend([f"자료: {m['source_status']}, 기간 {m['date_range']}, 원본 {m['raw_rows']}행 / 사용 {m['used_rows']}행.",
                                         f"데이터 버전: {m['dataset_version']}",''])
    if model:
        lines.extend([f"모델: {model['model_id']}, 상태: {model['source_status']}",
                      '독립 기간 검증은 조건부 관측 분포의 검증이며 인과효과의 검증은 아닙니다.',
                      '투구 목표 위치, 선수 능력, 컨택/파워 의도, 번트, 피로 효과, 전체 경기·수비·주루는 현재 연구 모델에서 미지원입니다.',''])
    if run:
        lines.extend([f"실행 ID: {run['run_id']}, 학습 실행: {run['training_executed']}",
                      '**보상은 출루 대리변수입니다. 경기 승리 학습이나 실제 경기 결과가 아닙니다.**',''])
    (output/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
