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


def build(result):
    pairs=[];counts=defaultdict(list);growth=defaultdict(list);games=0;pooled=new_stats()[0];signals=defaultdict(Counter)
    for seed in result['seeds']:
        history=seed['history']
        if not history:continue
        games+=history[-1]['games']
        for team in history[-1].get('strategy',new_stats()):merge([pooled],[team])
        initial={p['id']:p for p in history[0].get('strategy_probes',[])}
        for p in history[-1].get('strategy_probes',[]):
            if p['id'] not in initial:continue
            pair=(initial[p['id']]['teams'][0],p['teams'][0]);pairs.append(pair)
            if p['context'].get('name','').startswith('count_'):
                counts[p['context']['balls'],p['context']['strikes']].append(pair)
        # Older reports have first-pitch probes only; do not invent other counts.
        if not any(p['context'].get('name','').startswith('count_') for p in history[-1].get('strategy_probes',[])):
            for p in history[-1].get('strategy_probes',[]):
                if p['id'] in initial and not p['context'].get('name'):counts[p['context']['balls'],p['context']['strikes']].append((initial[p['id']]['teams'][0],p['teams'][0]))
        for h in history:
            for p in h.get('strategy_probes',[]):growth[h['games']].append((p['teams'][0],p['teams'][0]))
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
    answer={'games':games,'runs':len(result['seeds']),'target_games_per_run':result.get('config',{}).get('episodes',max(growth,default=0)),'offense':choice_groups(pooled['offense'],'offense'),
        'targets':pooled['targets'],'pitching':{k:v for k,v in choice_groups(pooled['defense'],'defense').items() if k!='intentional_walk'},
        'pitches':total_pitches,'preferences':average(pairs),
        'counts':[{'balls':b,'strikes':s,'preferences':average(counts[b,s])} for b in range(4) for s in range(3)],
        'growth':[{'games_per_run':n,'preferences':average(rows)} for n,rows in sorted(growth.items())],
        'feedback':feedback,'basis':'Observed virtual outcomes and pre-update terminal-win advantages; correlated within games, no causal explanation or transcript of thoughts.'}
    from .explanations import explain
    answer['explanations']=explain(answer,pooled['defense'],pooled['feedback']['defense'])
    return answer
