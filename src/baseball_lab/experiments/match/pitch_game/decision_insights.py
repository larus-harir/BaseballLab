"""Paired policy changes in recorded situations, not outcome tallies or causes."""
from collections import defaultdict
import json
from .explanations import FAMILIES, label, particle


def situation(context, view, *, brief=False):
    balls, strikes=context.get('balls',0),context.get('strikes',0)
    parts=[f'{balls}볼 {strikes}스트라이크' if not brief else f'{balls}B {strikes}S']
    if not brief and 'outs' in context:parts.append(f'{context["outs"]}아웃')
    if not brief and 'bases' in context:
        bases=context['bases']
        parts.append('주자 '+('·'.join(str(i+1)+'루' for i in range(3) if bases & (1<<i)) if bases else '없음'))
    # Pitching policies do not observe the incoming pitch cue used by batters.
    cue=(context.get('cue') or '').split(':')
    if view in ('offense','direction') and len(cue)>=3 and cue[1] in FAMILIES:
        height={'high':'높은','middle':'중간 높이의','low':'낮은'}.get(cue[2].split('_')[-1],'')
        parts.append((height+' ' if height else '')+FAMILIES[cue[1]]+('' if brief else ' 상대'))
    return ' · '.join(parts)


def build(result):
    # Local import avoids the overview/strategy-view import cycle.
    from .learning_overview import average
    groups=defaultdict(list)
    for run in result.get('seeds',[]):
        history=run.get('history',[])
        if len(history)<2 or history[-1]['games']<=history[0]['games']:continue
        initial={p['id']:p for p in history[0].get('strategy_probes',[])}
        seen=set()
        for probe in history[-1].get('strategy_probes',[]):
            key=probe['id'];old=initial.get(key)
            if key in seen or not old or old['context']!=probe['context']:continue
            seen.add(key)
            identity=(key,json.dumps(probe['context'],sort_keys=True))
            groups[identity].append((probe['context'],old['teams'][0],probe['teams'][0]))
    comparisons=[]
    for key,records in groups.items():
        pairs=[(old,new) for _,old,new in records]
        comparisons.append((key,records[0][0],average(pairs),[average([pair]) for pair in pairs]))
    stories=[]
    for view in ('offense','direction','defense','course'):
        candidates=[]
        for key,context,pooled,individual in comparisons:
            values=pooled[view]
            if not values['states']:continue
            before,after=values['before'],values['after']
            keys=before.keys()|after.keys()
            deltas={a:after.get(a,0)-before.get(a,0) for a in keys}
            # Describe pitch selection where it is recorded. Generic pitching
            # versus an intentional walk is a separate decision, not a style.
            choices=[a for a in keys if a.startswith('family:')] if view=='defense' else keys
            if not choices:continue
            action=max(sorted(choices),key=lambda a:(abs(deltas[a]),deltas[a]))
            replaced=(min if deltas[action]>=0 else max)(sorted(keys),key=lambda a:deltas[a])
            shifts=[]
            for run in individual:
                v=run[view]
                if v['states']:shifts.append(v['after'].get(action,0)-v['before'].get(action,0))
            candidates.append((deltas[action],key,context,values,action,replaced,shifts))
        if not candidates:continue
        delta,key,context,values,action,replaced,shifts=max(candidates,key=lambda row:(abs(row[0]),row[0],row[1]))
        name=label(action);where=situation(context,view)
        changed=abs(delta)>=.02  # Readability threshold, not a significance test.
        increased,decreased=(name,label(replaced)) if delta>=0 else (label(replaced),name)
        summary=(where+'에서는 '+particle(increased,'을','를')+' 더 고르고 '+particle(decreased,'은','는')+' 덜 고르게 됐습니다.' if changed
                 else '비교한 상황에서 '+{'offense':'타격 판단','direction':'타격 방향','defense':'구종·승부','course':'코스'}[view]+' 선호는 크게 바뀌지 않았습니다.')
        if len(shifts)<2:reason='같은 상황의 학습 전후 선택 확률을 비교했습니다. 다른 실행에서도 반복되는지는 아직 확인할 수 없습니다.'
        elif min(shifts)>1e-9 or max(shifts)<-1e-9:reason=f'이 선택은 비교 가능한 {len(shifts)}개 실행 모두에서 '+('늘었습니다.' if delta>0 else '줄었습니다.')
        elif max(abs(x) for x in shifts)<=1e-9:reason='같은 상황의 학습 전후 선택 확률에 변화가 없습니다.'
        else:reason='실행마다 변화 방향이 달랐습니다. 하나의 전략으로 자리 잡았다고 보기는 이릅니다.'
        if view=='direction':reason+=' 방향을 정한 스윙 안에서 비교한 선호입니다.'
        elif view=='course':reason+=' 코스를 정한 투구 안에서 비교한 선호입니다.'
        rows=[{'action':a,'before':values['before'].get(a,0),'after':values['after'].get(a,0)} for a in (action,replaced) if a]
        if action==replaced:rows=rows[:1]
        scope=context.get('environment','').split(':')[:2]
        if context.get('hand') in ('R','L','S'):scope.append({'R':'우타자','L':'좌타자','S':'양타자'}[context['hand']])
        if 'inning' in context:scope.append(str(context['inning'])+'회'+('말' if context.get('bottom') else '초'))
        if 'difference' in context:
            diff=context['difference'];scope.append('공격 팀 '+(f'{diff}점 앞섬' if diff>0 else f'{-diff}점 뒤짐' if diff<0 else '동점'))
        stories.append({'view':view,'action':action,'title':name,'summary':summary,'reason':reason,
            'context':' · '.join(scope),'state':where,'brief_state':situation(context,view,brief=True),
            'before':values['before'].get(action,0),'after':values['after'].get(action,0),
            'delta':delta,'decisions':0,'signal':None,'pattern':None,'observed':'',
            'comparison':rows,'preferences':values,'matched_runs':len(shifts),'run_deltas':shifts,'probe_id':key[0],'situation_specific':True})
    return stories
