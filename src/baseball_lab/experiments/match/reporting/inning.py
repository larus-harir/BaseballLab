"""Readable run-maximization report; does not reinterpret the R1 reward."""
import json
import math
from pathlib import Path
from baseball_lab.data.protection import public_view
from baseball_lab.data.lineage import write_json
from baseball_lab.web.scene_assets import embed


def estimate(values):
    if not values:return None
    mean = sum(values)/len(values)
    se = math.sqrt(sum((x-mean)**2 for x in values)/(len(values)-1)/len(values)) if len(values)>1 else 0.
    return {'mean':mean,'n':len(values),'interval':[mean-1.96*se,mean+1.96*se]}


def summary(result):
    finished = [s for s in result['seeds'] if 'test_evaluation' in s]
    def row(rows,role,opponent):
        return next(r for r in rows if r['learner_role']==role and r['opponent']==opponent)
    current = estimate([v for s in finished for v in row(s['test_evaluation'],'both','self')['runs_by_inning']])
    growth = []
    for role,label in (('batter','공격 AI'),('pitcher','수비 AI')):
        before=[];after=[];changes=[];by_seed=[]
        for s in finished:
            a=row(s['initial_test_evaluation'],role,'fixed')['runs_by_inning']
            z=row(s['test_evaluation'],role,'fixed')['runs_by_inning']
            before.extend(a);after.extend(z)
            diffs=[(y-x)*(1 if role=='batter' else -1) for x,y in zip(a,z)]
            changes.extend(diffs);by_seed.append({'seed':s['seed'],**estimate(diffs)})
        delta=estimate(changes)
        verdict='평가 중'
        if delta:
            lo,hi=delta['interval']
            verdict='좋아졌습니다' if lo>0 else '나빠졌습니다' if hi<0 else '뚜렷한 개선을 확인하지 못했습니다'
            if (lo>0 and any(s['mean']<=0 for s in by_seed)) or (hi<0 and any(s['mean']>=0 for s in by_seed)):
                verdict='반복에 따라 결과가 달라졌습니다'
        growth.append({'role':role,'label':label,'before':estimate(before),'after':estimate(after),
                       'change':delta,'by_seed':by_seed,'verdict':verdict})
    choices=[]
    for attribute,label in (('bunt_probability','공격의 번트 선택'),('intentional_walk_probability','수비의 고의볼넷 선택')):
        before=[];after=[]
        for s in result['seeds']:
            if len(s['history'])<2:continue
            a,z=s['history'][0]['policy_probes'],s['history'][-1]['policy_probes']
            for x,y in zip(a,z):
                if attribute=='bunt_probability' and not x['bunt_supported']:continue
                before.append(x[attribute]);after.append(y[attribute])
        if before:choices.append({'label':label,'before':sum(before)/len(before),'after':sum(after)/len(after),
                                   'scope':'같은 아웃·주자 상황을 동일 비중으로 비교한 선택 확률입니다. 실제 선택 횟수나 사람의 방문 빈도가 아닙니다.'})
    return {'complete':result['status']=='COMPLETED','finished_repeats':len(finished),'choices':choices,
            'planned_repeats':len(result['config']['seeds']),'current':current,'growth':growth,
            'headline':f"학습한 두 AI의 맞대결: 이닝당 {current['mean']:.2f}점" if current else '학습 중 · 중간 변화부터 확인하세요',
            'growth_headline':' / '.join(g['label']+' '+g['verdict'] for g in growth),
            'scope':'무사·주자 없음에서 세 아웃까지의 총득점입니다. 득점만으로 공격·수비의 우열이나 9이닝 승률을 정하지 않습니다.',
            'uncertainty':'범위는 시뮬레이션 추첨 오차의 근사치입니다. 반복별 차이·실제 자료의 편향·모형 오차는 별도로 봐야 합니다.'}


def render(result):
    payload=json.dumps(public_view({**result,'reading':summary(result)}),ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    return embed(Path(__file__).with_name('inning.html').read_text(encoding='utf-8')).replace('__RESEARCH__',payload)


def report(output,result):
    output=Path(output)
    (output/'report.html').write_text(render(result),encoding='utf-8')
    write_json(output/'summary.json',summary(result))
