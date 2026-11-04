"""Deterministic reading of existing evidence; no LLM narrative or new evaluation.

Head-to-head success is separate from growth against an unchanged opponent.
Intervals describe simulation sampling only, never real-baseball generality.
"""
from statistics import mean
from baseball_lab.evaluation.metrics import wilson_interval


def pool(rows, *, defense=False):
    rows = list(rows)
    if not rows:
        return None
    if len({r.get('environment_id') for r in rows})>1:
        raise ValueError('서로 다른 평가 환경의 성공률을 하나의 우세 판정으로 합칠 수 없습니다.')
    n = sum(r['n'] for r in rows)
    wins = sum((r['n']-r['scored']) if defense else r['scored'] for r in rows)
    return {'n': n, 'successes': wins, 'rate': wins/n, 'ci95': list(wilson_interval(wins, n)),
            'repeats': len(rows), 'repeat_rates': [(r['n']-r['scored'] if defense else r['scored'])/r['n'] for r in rows]}


def find(run, stage, role, opponent):
    return next((e for e in run.get(stage, []) if e['learner_role']==role and e['opponent']==opponent), None)


def verdict(result):
    if result is None:
        return 'pending', '평가를 기다리고 있어요'
    lo, hi = result['ci95']; rates = result['repeat_rates']
    if result['repeats'] < 2:
        return 'uncertain', '우세 판단 보류 · 반복 확인이 더 필요해요'
    if lo > .5 and all(r > .5 for r in rates):
        return 'offense', '이번 조건에서는 공격 쪽 우세'
    if hi < .5 and all(r < .5 for r in rates):
        return 'defense', '이번 조건에서는 수비 쪽 우세'
    return 'uncertain', '우세 판단 보류 · 결과 차이가 뚜렷하지 않아요'


def build_summary(result):
    runs = result.get('seeds', [])
    finished = [r for r in runs if find(r,'test_evaluation','both','self')]
    duel = pool(find(r,'test_evaluation','both','self') for r in finished)
    code, title = verdict(duel)
    complete = result['status']=='COMPLETED' and len(finished)==len(result['config']['seeds'])
    if not complete:
        code, title = 'pending', '학습 중 · 최종 우세는 아직 평가하지 않았어요'
    growth=[]
    for role, label in (('batter','공격'), ('pitcher','수비')):
        valid=[r for r in finished if find(r,'initial_test_evaluation',role,'fixed') and find(r,'test_evaluation',role,'fixed')]
        before=pool((find(r,'initial_test_evaluation',role,'fixed') for r in valid), defense=role=='pitcher')
        after=pool((find(r,'test_evaluation',role,'fixed') for r in valid), defense=role=='pitcher')
        if not before or not after:
            growth.append({'role': role,'label':label,'before':None,'after':None,'text':'최종 평가 대기'});continue
        deltas=[a-b for a,b in zip(after['repeat_rates'],before['repeat_rates'])]
        # Conservative interval arithmetic; same-random-stream pairing is not
        # reconstructed from aggregates. Do not claim a paired significance test.
        bounds=[after['ci95'][0]-before['ci95'][1],after['ci95'][1]-before['ci95'][0]]
        improved=len(deltas)>=2 and min(deltas)>0 and bounds[0]>0
        worsened=len(deltas)>=2 and max(deltas)<0 and bounds[1]<0
        text='모든 반복에서 개선 방향이 확인됐어요' if improved else '모든 반복에서 성적이 낮아졌어요' if worsened else '뚜렷한 성적 개선은 확인되지 않았어요'
        growth.append({'role':role,'label':label,'before':before,'after':after,'delta_pp':100*(after['rate']-before['rate']),
                       'improved':improved,'text':text,'difference_bounds':bounds})
    improved=[g['label'] for g in growth if g.get('improved')]
    growth_title=f"학습 전보다 좋아진 쪽: {'·'.join(improved)}" if improved else '학습 전보다 뚜렷하게 좋아진 쪽은 아직 없어요'
    if not complete:growth_title='학습 전후 성적은 최종 평가 후 정리합니다'
    timeline=[]
    # Diagonal cross-play uses a single held-out environment, unlike a graph
    # that silently compares validation-period checkpoints with test-period final.
    steps=sorted({e['batter_episode'] for r in finished for e in r.get('cross_play',[]) if e['batter_episode']==e['pitcher_episode']})
    for step in steps:
        rows=[next(e for e in r['cross_play'] if e['batter_episode']==step and e['pitcher_episode']==step)
              for r in finished if any(e['batter_episode']==step and e['pitcher_episode']==step for e in r.get('cross_play',[]))]
        value=pool(rows)
        timeline.append({'episodes':step,**value})
    choices=[]
    for field,label in (('bunt_probability','번트 선택'),('intentional_walk_probability','고의볼넷 선택')):
        pairs=[]
        for run in runs:
            history=run.get('history',[])
            if not history:continue
            def average(h):
                probes=[p for p in h['policy_probes'] if field!='bunt_probability' or p['bunt_supported']]
                return mean(p[field] for p in probes) if probes else None
            a,b=average(history[0]),average(history[-1])
            if a is not None and b is not None:pairs.append((a,b))
        if not pairs:continue
        before,after=mean(p[0] for p in pairs),mean(p[1] for p in pairs)
        differences=[b-a for a,b in pairs]
        direction='반복마다 방향이 달라요' if min(differences)<0<max(differences) else '줄어들었어요' if max(differences)<0 else '늘어났어요' if min(differences)>0 else '뚜렷한 방향이 없어요'
        choices.append({'field':field,'label':label,'before':before,'after':after,'text':direction,
                        'scope':'지원되는 같은 아웃·주자 상황의 평균 선택 확률'})
    return {'version':'match-summary-v1','complete':complete,'verdict':code,'headline':title,'duel':duel,
            'growth_headline':growth_title,'growth':growth,'timeline':timeline,'choices':choices,
            'episodes_per_repeat':result['config']['episodes'],'planned_repeats':len(result['config']['seeds']),
            'finished_repeats':len(finished),
            'scope':'한 점 득점 실험에서 24개 아웃·주자 상태를 같은 비중으로 시작한 결과입니다. 실제 경기 승률이나 AI 실력의 일반적 우열은 아닙니다.',
            'uncertainty':'95% 구간은 가상 대결의 표본 오차만 반영합니다. 우세는 구간이 50%를 벗어나고 반복마다 방향이 같을 때 표시합니다. 여러 학습 시점의 유의성 검정은 하지 않습니다.'}
