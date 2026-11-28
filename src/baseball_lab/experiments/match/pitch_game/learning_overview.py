"""Pooled learning evidence; associations are not AI thoughts or causal effects."""
from collections import Counter,defaultdict
from .strategy import new_stats,merge
from .strategy_view import choice_groups

VIEWS=('offense','direction','defense','course')


def conditional(values,view):
    values=choice_groups(values,view);n=sum(values.values())
    return {k:v/n for k,v in values.items()} if n else {}


def average(pairs):
    answer={}
    for view in VIEWS:
        before=Counter();after=Counter();n=0
        for old,new in pairs:
            role='offense' if view in ('offense','direction') else 'defense'
            a,b=conditional(old[role],view),conditional(new[role],view)
            if not a or not b:continue
            n+=1;before.update(a);after.update(b)
        answer[view]={'states':n,'before':{k:v/n for k,v in before.items()},'after':{k:v/n for k,v in after.items()}}
    return answer


def compare_overall(preferences, run_preferences):
    """Rank changes in the paired averages, independently of executed counts."""
    result={}
    for view,values in preferences.items():
        rows=[]
        for action in values['before'].keys()|values['after'].keys():
            before=values['before'].get(action,0)
            after=values['after'].get(action,0)
            shifts=[run[view]['after'].get(action,0)-run[view]['before'].get(action,0)
                    for run in run_preferences if run[view]['states']]
            rows.append({'action':action,'before':before,'after':after,'delta':after-before,
                         'up':sum(d>1e-9 for d in shifts),'down':sum(d<-1e-9 for d in shifts),
                         'runs':len(shifts)})
        result[view]=sorted(rows,key=lambda row:(-abs(row['delta']),-row['after'],row['action']))
    return result


def build(result):
    pairs=[];runs=[];counts=defaultdict(list);games=0;pooled=new_stats()[0];signals=defaultdict(Counter)
    for seed in result['seeds']:
        history=seed['history']
        if not history:continue
        games+=history[-1]['games']
        for team in history[-1].get('strategy',new_stats()):merge([pooled],[team])
        initial={p['id']:p for p in history[0].get('strategy_probes',[])}
        probes=history[-1].get('strategy_probes',[])
        count_probes=any(p['context'].get('name','').startswith('count_') for p in probes)
        run=[]
        if history[-1]['games']>history[0]['games']:
            for p in probes:
                old=initial.get(p['id']);context=p['context']
                if old is None or old['context']!=context:continue
                pair=(old['teams'][0],p['teams'][0]);run.append(pair)
                name=context.get('name','')
                # Older reports have first-pitch probes only.
                if name.startswith('count_') or (not name and not count_probes):
                    counts[context['balls'],context['strikes']].append(pair)
        if run:pairs.extend(run);runs.append(average(run))
        for update in seed.get('learning_updates',[]):
            for key,row in update.get('choice_signals',{}).items():signals[key].update(row)
    feedback={v:{} for v in VIEWS}
    for view in VIEWS:
        role='offense' if view in ('offense','direction') else 'defense'
        for action,row in pooled['feedback'][role].items():
            for key in choice_groups({action:1},view):
                target=feedback[view].setdefault(key,{})
                merge([target],[row])
        for key,row in feedback[view].items():
            group='family' if view=='defense' and key.startswith('family:') else view
            signal_key=group+':'+key.split(':')[-1]
            signal=signals.get(signal_key,{})
            n=signal.get('decisions',0);row['reward_observations']=n
            row['mean_advantage']=signal['advantage_sum']/n if n else None
            row['winning_game_share']=signal['wins']/n if n else None
    total_pitches=sum(n for a,n in pooled['defense'].items() if a=='pitch' or a.startswith('pitch:'))
    preferences=average(pairs)
    answer={'games':games,'runs':len(result['seeds']),'offense':choice_groups(pooled['offense'],'offense'),
        'targets':pooled['targets'],'pitching':{k:v for k,v in choice_groups(pooled['defense'],'defense').items() if k!='intentional_walk'},
        'pitches':total_pitches,'preferences':preferences,'overall':compare_overall(preferences,runs),
        'counts':[{'balls':b,'strikes':s,'preferences':average(counts[b,s])} for b in range(4) for s in range(3)],
        'feedback':feedback,'basis':'Observed virtual outcomes and pre-update terminal-win advantages; correlated within games, no causal explanation or transcript of thoughts.'}
    from .explanations import explain
    from .decision_insights import build as insights
    answer['explanations']=insights(result) or explain(answer,pooled['defense'],pooled['feedback']['defense'])
    return answer
