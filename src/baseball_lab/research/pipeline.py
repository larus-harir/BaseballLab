"""One request: period selection, verified source/cache, calibration, validation, learning."""
from dataclasses import dataclass
from datetime import date,timedelta
from pathlib import Path

from baseball_lab.data.lineage import RawSource,content_hash,write_json
from baseball_lab.data.statcast import acquire,audit,load_dataset
from baseball_lab.outcome.empirical import fit,load_model
from baseball_lab.tracking.evidence_report import write_report


@dataclass(frozen=True)
class Plan:
    start: str
    end: str

    def __post_init__(self):
        days=(date.fromisoformat(self.end)-date.fromisoformat(self.start)).days+1
        if not 3<=days<=14:raise ValueError('최초 자동 실험 기간은 3~14일로 선택하세요. 세 독립 구간이 필요합니다.')

    @property
    def boundaries(self):
        first=date.fromisoformat(self.start)
        days=(date.fromisoformat(self.end)-first).days+1
        fitting=max(1,days//2)
        validation=max(1,(days-fitting)//2)
        return (first+timedelta(days=fitting)).isoformat(),(first+timedelta(days=fitting+validation)).isoformat()


def selected_dataset(cached,plan,output):
    manifest=cached['manifest']
    records=[row for row in cached['records'] if plan.start<=row['game_date']<=plan.end]
    if not records:raise ValueError('선택한 기간에 사용 가능한 투구가 없습니다.')
    m={**manifest,'used_rows':len(records),'games':len({r['game_pk'] for r in records}),
       'date_range':[min(r['game_date'] for r in records),max(r['game_date'] for r in records)],
       'selection':{'requested_dates':[plan.start,plan.end],'parent_dataset_version':manifest['dataset_version'],
                    'outside_selected_period':len(cached['records'])-len(records),
                    'missingness_scope':'raw source files; selected record count is used_rows'},
       'normalized_checksum':content_hash(records)}
    m['dataset_version']=content_hash({k:m[k] for k in ('schema_version','normalized_checksum','source_status')})
    data={'manifest':m,'records':records};write_json(output/'dataset.json',data);write_json(output/'quality.json',m)
    return data


def run(plan,data_dir,output,*,episodes=600,seed=20261104,authorization_reference=None,test_only=False,progress=print):
    output=Path(output);data_dir=Path(data_dir)
    if output.exists() and any(output.iterdir()):raise ValueError('새 실행 폴더가 필요합니다.')
    output.mkdir(parents=True)
    before,test_from=plan.boundaries
    write_json(output/'plan.json',{'start':plan.start,'end':plan.end,'train_before':before,'test_from':test_from,
                                 'episodes':episodes,'seed':seed,'status':'preparing'})
    try:
        progress('단계 1/4 · 선택한 기간의 실제 자료를 찾고 있어요.',flush=True)
        cached=None
        cached_path=data_dir/'dataset.json'
        if cached_path.exists():
            candidate=load_dataset(cached_path)
            low,high=candidate['manifest']['date_range']
            if low<=plan.start and plan.end<=high:cached=candidate
        if cached is None:
            # No request is made without a separately supplied, persistent authorization basis.
            if not authorization_reference:
                raise PermissionError('선택 기간의 확인된 자료가 없습니다. 현재 공식 사이트의 자동 수집 제한 때문에 허용 근거 없이 가져올 수 없습니다. 자료 제공 연결을 한 번 설정해야 자동 실행할 수 있습니다. 기존 자료로 몰래 대체하지 않았습니다.')
            acquisition=acquire(plan.start,plan.end,output/'raw',usage_note='Date-configured local research; no redistribution grant',authorization_reference=authorization_reference)
            cached=audit([RawSource(**s) for s in acquisition['sources']],data_dir)
        dataset=selected_dataset(cached,plan,output/'data')
        progress(f"단계 2/4 · {len(dataset['records']):,}개 투구로 모델을 만들고 있어요.",flush=True)
        artifact=fit(output/'data/dataset.json',output/'data',train_before=before,test_from=test_from,test_only=test_only,
                     **({'min_support':1,'min_fit_rows':1,'min_holdout_rows':1} if test_only else {}))
        progress('단계 3/4 · 사용하지 않은 기간으로 모델을 검사하고 있어요.',flush=True)
        write_report(output,dataset=dataset,model=artifact)
        model,_=load_model(output/'data/model.json',test_only=test_only)
        progress('단계 4/4 · 검사한 환경에서 두 신경망의 학습을 시작합니다.',flush=True)
        from baseball_lab.research.training import ResearchConfig,train
        result=train(ResearchConfig(episodes=episodes,seed=seed,evaluate_every=min(episodes,200)),
                     output/'data/model.json',output/'learning',test_only=test_only,progress=progress)
        # Report redirects remain a relative file within this run; shared viewer is unchanged.
        (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=learning/report.html"><a href="learning/report.html">학습 결과 열기</a>',encoding='utf-8')
        write_json(output/'plan.json',{'start':plan.start,'end':plan.end,'train_before':before,'test_from':test_from,
                    'episodes':episodes,'seed':seed,'status':'completed','model_id':artifact['model_id'],
                    'run_id':result['run_id'],'source_dataset_version':dataset['manifest']['dataset_version']})
        return result
    except Exception as exc:
        # Preserve an already written validation report; failures never turn into synthetic training.
        if not (output/'report.html').exists():write_report(output,failure={'error':str(exc),'research_executed':False})
        write_json(output/'failure.json',{'error':str(exc),'synthetic_fallback':False,'research_completed':False})
        raise
