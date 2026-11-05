"""Independent observation session using the existing empirical R1 adapter.

No training import, optimizer, or checkpoint update. An observed source segment
and a model-generated one-run scenario have separate records and UI labels.
"""
from pathlib import Path
from random import Random
import json

from baseball_lab.data.lineage import write_json
from baseball_lab.r1.environment import fit
from baseball_lab.web.scene_assets import embed
from baseball_lab.data.protection import public_view


class SessionPolicy:
    def __init__(self, style):
        if style not in ('basic','random'):raise ValueError('지원하지 않는 관찰 정책')
        self.style=style

    def act(self, obs, legal, rng):
        return legal[0] if self.style=='basic' else rng.choice(legal)


def observe(dataset,start,end,output,*,seed=41,outs=0,bases=1,source='model',style='basic',test_only=False):
    if dataset['manifest']['source_status']!='REAL_OBSERVED' and not test_only:
        raise ValueError('실제 원천 자료가 필요합니다.')
    if type(seed) is not int or not 0<=seed<=2**31-1:raise ValueError('재현 번호 범위를 확인하세요.')
    if type(outs) is not int or not 0<=outs<=2 or type(bases) is not int or not 0<=bases<=7:
        raise ValueError('시작 아웃·주자 상태를 확인하세요.')
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('기존 결과를 덮어쓰지 않습니다.')
    if source=='observed':
        rows=[r for r in dataset['records'] if start<=r['date']<=end and r['outs']==outs and r['bases']==bases]
        if not rows:raise ValueError('이 상황의 실제 기록이 없습니다.')
        r=Random(seed).choice(rows)
        events=[{'before':{'outs':outs,'bases':bases},'after':{'outs':outs+r['outs_added'],'bases':r['end_bases']},
                 'runs':r['runs'],'source_row_ids':r['source_row_ids'],'record_id':r['record_id'],
                 'inning':r.get('inning'),'bottom':r.get('bottom'),'game_id':r['game_id'],'source_status':'REAL_OBSERVED','event_codes':r['event_codes']}]
        label='실제 원천의 관측 턴';policies='AI가 선택한 플레이가 아닙니다.'
    elif source=='model':
        envs,_=fit(dataset,start,end)
        _,events=envs['test'].play(SessionPolicy(style),SessionPolicy(style),seed,start=(outs,bases),record=True)
        label='모델이 생성한 한 점 득점 상황';policies='양쪽 모두 고정 기본 정책' if style=='basic' else '양쪽 모두 고정 무작위 정책'
    else:raise ValueError('실제 기록 또는 모델 관찰을 선택하세요.')
    result={'schema':'baseball-lab-observation-v1','training_executed':False,'label':label,'policies':policies,
            'dataset_id':dataset['manifest']['dataset_id'],'source_status':'REAL_OBSERVED' if source=='observed' else 'MODEL_SIMULATED',
            'style':style,'season':start[:4],'seed':seed,'events':events,'credit':dataset['manifest']['credit']}
    if test_only:
        result['source_status']='MOCK_TEST_ONLY'
        for event in result['events']:event['source_status']='MOCK_TEST_ONLY'
    output.mkdir(parents=True);write_json(output/'session.json',result)
    (output/'report.html').write_text(render(result),encoding='utf-8')
    return result


def render(result):
    payload=json.dumps(public_view(result),ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    template=embed(Path(__file__).with_name('session.html').read_text(encoding='utf-8'))
    return template.replace('__SESSION__',payload)
