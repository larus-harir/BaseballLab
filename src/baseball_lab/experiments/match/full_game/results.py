"""Read-only team explanations over saved runs; never recompute a game or fit."""
from collections import Counter
import json
from pathlib import Path

OFF=('ordinary_turn','early_swing','take_first','bunt_attempt','steal_attempt')


def team_game(events,side,names):
    attack=[e for e in events if e['bottom']==side]
    defense=[e for e in events if e['bottom']!=side]
    choices=Counter(e['offense'] for e in attack)
    pitching=Counter(e['defense'] for e in defense if e['offense']!='steal_attempt')
    steals=[e for e in attack if e['offense']=='steal_attempt']
    main=choices.most_common(1)
    return {'runs':sum(e['runs'] for e in attack),'allowed_runs':sum(e['runs'] for e in defense),
        'attack_scenes':len(attack),'outs_taken':sum(e['after']['outs']-e['before']['outs'] for e in defense),
        'attack_choices':[{'key':k,'label':names.get(k,k),'count':choices[k]} for k in OFF if choices[k]],
        'pitch_choices':[{'key':k,'label':names.get(k,k),'count':pitching[k]} for k in ('challenge','intentional_walk') if pitching[k]],
        'steal_attempts':len(steals),'steal_out_scenes':sum(e['after']['outs']>e['before']['outs'] for e in steals),
        'main_choice':({'label':names.get(main[0][0],main[0][0]),'count':main[0][1]} if main else None)}


def changes(seed,names):
    history=seed.get('history',[])
    if len(history)<2:return []
    old={(p['role'],p['inning'],p['difference']):p for p in history[0].get('probes',[])}
    rows=[]
    for probe in history[-1].get('probes',[]):
        previous=old.get((probe['role'],probe['inning'],probe['difference']))
        if previous is None:continue
        for action,after in probe['probabilities'].items():
            before=previous['probabilities'].get(action)
            if before is None or abs(after-before)<1e-9:continue
            rows.append({'role':probe['role'],'inning':probe['inning'],'difference':-probe['difference'] if probe['role']=='수비' else probe['difference'],
                'action':names.get(action,action),'before':before,'after':after,'delta':after-before})
    # Separate offense/defense so the summary doesn't bury one network's changes.
    return [max((r for r in rows if r['role']==role),key=lambda r:abs(r['delta']),default=None) for role in ('공격','수비')]


def explain(result):
    names=result['action_names'];completed=[s for s in result.get('seeds',[]) if 'test_before' in s and 'test_after' in s]
    totals={stage:{'games':sum(s[stage]['games'] for s in completed),'wins':sum(s[stage]['wins'] for s in completed)} for stage in ('test_before','test_after')}
    before,after=totals['test_before'],totals['test_after']
    if after['games']:
        delta=after['wins']/after['games']-before['wins']/before['games']
        winner='A팀' if after['wins']>after['games']-after['wins'] else 'B팀' if after['wins']<after['games']-after['wins'] else '동률'
        headline=f"평가 {after['games']}경기: A팀 {after['wins']}승 · B팀 {after['games']-after['wins']}승"
        growth=f"A팀 승률 {100*before['wins']/before['games']:.1f}% → {100*after['wins']/after['games']:.1f}% ({abs(delta)*100:.1f}%p {'상승' if delta>0 else '하락' if delta<0 else '변화 없음'})"
    else:headline='학습 후 평가를 기다리고 있습니다';growth='평가가 끝나면 두 팀의 승패와 A팀의 학습 전후 변화를 보여줍니다.';winner=None
    runs=[]
    for i,s in enumerate(result.get('seeds',[]),1):
        replay=s.get('replay');events=replay.get('events',[]) if replay else []
        # v1 writer explicitly records the learner at home against Fixed/Fixed.
        learner_home=bool(replay.get('learner_home',True)) if replay else True
        teams={}
        for label,side in (('A',int(learner_home)),('B',1-int(learner_home))):
            teams[label]={'label':label+'팀','side':side,'venue':'홈' if side else '원정','kind':'학습한 AI' if label=='A' else '고정 비교 상대',
                **team_game(events,side,names)}
        innings=[]
        for inning in range(1,(replay.get('innings',0) if replay else 0)+1):
            row={'inning':inning}
            for label,team in teams.items():
                half=[e for e in events if e['inning']==inning and e['bottom']==team['side']]
                row[label]=sum(e['runs'] for e in half) if half else None
            innings.append(row)
        scenes=[]
        for e in events:
            batting='A' if e['bottom']==int(learner_home) else 'B';fielding='B' if batting=='A' else 'A'
            scenes.append({'inning':e['inning'],'half':'말' if e['bottom'] else '초','attack':batting,'defense':fielding,
                'outs':e['before']['outs'],'bases':e['before']['bases'],'after_outs':e['after']['outs'],'after_bases':e['after']['bases'],
                'offense_choice':names.get(e['offense'],e['offense']),'defense_choice':names.get(e['defense'],e['defense']) if e['offense']!='steal_attempt' else '투구 전 도루 장면',
                'runs':e['runs'],'A':e['scores'][int(learner_home)],'B':e['scores'][1-int(learner_home)]})
        runs.append({'number':i,'seed':s['seed'],'ready':bool(events),'teams':teams,'innings':innings,'scenes':scenes,
            'changes':[c for c in changes(s,names) if c],
            'winner':('A' if teams['A']['runs']>teams['B']['runs'] else 'B') if events else None,
            'history':[{'games':h['games'],'win_rate':h['validation']['win_rate']} for h in s.get('history',[])],
            'evaluation':{k:s[k] for k in ('test_before','test_after') if k in s}})
    return {'headline':headline,'growth':growth,'evaluation':totals,'evaluation_leader':winner,'runs':runs,
        'training_games':sum(s.get('history',[{}])[-1].get('games',0) for s in result.get('seeds',[]) if s.get('history')),
        'status':result.get('status'),'supported_actions':[names.get(a,a) for a in result['supported_actions']],
        'role_note':'A팀은 공격 담당·수비 담당 신경망을 학습한 팀입니다. B팀은 일반 타격과 승부를 고정한 평가용 상대입니다. 각 타석의 선수 9명을 따로 학습시킨 결과는 아닙니다.'}


def render(result):
    payload={'view':explain(result),'evidence':{k:result.get(k) for k in ('run_id','reward','rules','split','dataset','limitations','source_hash','code_commit')}}
    data=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return Path(__file__).with_name('results.html').read_text(encoding='utf-8').replace('__RESULT__',data)
