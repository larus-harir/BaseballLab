"""Executed choices and fixed-state preferences, without claims about AI thoughts."""
from baseball_lab.data.batting_directions import CONTACT


def new_stats():
    return [{'offense':{},'defense':{},'opportunities':{'offense':{},'defense':{}},'pitch_family':{},'pitch_area':{},
             'pitch_bins':{'selected':{},'generated':{}},'management':{'games':0,'changes':0,'histogram':{},'invalid_changes':0},
             'targets':{},'batted_area':{},'batted_kind':{},'feedback':{'offense':{},'defense':{}},'environments':{}} for _ in (0,1)]


def increment(table,key,n=1):table[key]=table.get(key,0)+n


def observe(stats,batting,defense,offense,event,legal_offense,legal_defense,observation,contact,environment):
    for i,role,action,legal in ((batting,'offense',offense,legal_offense),(1-batting,'defense',defense,legal_defense)):
        if action is None:continue
        team=stats[i];increment(team[role],action);increment(team['environments'],environment)
        for option in legal:increment(team['opportunities'][role],option)
        feedback=team['feedback'][role].setdefault(action,{'decisions':0,'contact':0,'hits':0,'home_runs':0})
        feedback['decisions']+=1;feedback['contact']+=int(event in CONTACT)
        feedback['hits']+=int(event in ('single','double','triple','home_run'));feedback['home_runs']+=int(event=='home_run')
        increment(feedback.setdefault('events',{}),event)
        if event in CONTACT and contact and contact.get('kind'):increment(feedback.setdefault('kinds',{}),contact['kind'])
    if offense is not None:
        team=stats[batting]
        if offense.startswith('swing:'):increment(team['targets'],offense.split(':')[1])
        if event in CONTACT:
            increment(team['batted_area'],(contact or {}).get('side') or 'unknown')
            increment(team['batted_kind'],(contact or {}).get('kind') or 'unknown')
    if defense=='pitch' or defense.startswith('pitch:'):
        team=stats[1-batting];increment(team['pitch_family'],observation.pitch_family_cue or 'unknown')
        increment(team['pitch_area'],observation.location_cue or 'unknown')
        for mode,family,area in (('generated',observation.pitch_family_cue or 'unknown',observation.location_cue or 'unknown'),
                                ('selected',*(defense.split(':')[1:3] if defense.startswith('pitch:') else ('unspecified','unknown')))):
            bins=team['pitch_bins'][mode].setdefault(environment,{}).setdefault(family,{})
            increment(bins,area)


def settle(stats,batting,defense,offense,outs,runs,terminal=None):
    for i,role,action in ((batting,'offense',offense),(1-batting,'defense',defense)):
        if action is None:continue
        row=stats[i]['feedback'][role][action]
        if terminal:increment(row.setdefault('terminal_results',{}),terminal)
        for key,n in (('outs',outs),('runs',runs),('strikeouts',int(terminal=='strikeout'))):increment(row,key,n)


def merge(target,source):
    for team,addition in zip(target,source):
        def add(a,b):
            for k,v in b.items():
                if isinstance(v,dict):add(a.setdefault(k,{}),v)
                else:a[k]=a.get(k,0)+v
        add(team,addition)
    return target


def analyze(result):
    combined=new_stats();probes=[];phases=[]
    for seed in result['seeds']:
        history=seed['history']
        if not history:continue
        merge(combined,history[-1].get('strategy',new_stats()))
        before={p['id']:p for p in history[0].get('strategy_probes',[])}
        for p in history[-1].get('strategy_probes',[]):
            old=before.get(p['id'])
            if old:probes.append({'seed':seed['seed'],'context':p['context'],'teams':[
                {role:{'before':old['teams'][i][role],'after':p['teams'][i][role]} for role in ('offense','defense')} for i in (0,1)]})
        phases.append({'seed':seed['seed'],'checkpoints':[{'games':h['games'],'strategy':h.get('strategy',new_stats())} for h in history]})
    return {'schema':'baseball-strategy-analysis-v1','teams':combined,'preferences':probes,'growth':phases,
        'interpretation':'Choice frequency describes executed behavior; same-state policy probabilities describe learned preference, not proven optimality or a transcript of reasoning.'}


def complete_game(stats,choices,traces):
    """Each completed game must reconcile its actual substitution decisions."""
    for team,counts,trace in zip(stats,choices,traces):
        count=sum(counts.get(k,0) for k in ('change_1','change_2'))
        used={0};previous=0
        if count!=len(trace) or count>2:raise ValueError('투수 교체 원장과 행동 집계가 맞지 않습니다.')
        for change in trace:
            if (change['from_slot']!=previous or change['to_slot'] in used or change['to_slot'] not in (1,2)
                    or not change.get('has_appeared') or not (change['inning_break'] or change['batters_faced']>=3)):
                raise ValueError('투수 재등판·최소 상대 타자 규칙 검사 실패')
            used.add(change['to_slot']);previous=change['to_slot']
        m=team['management'];m['games']+=1;m['changes']+=count;increment(m['histogram'],str(count))
