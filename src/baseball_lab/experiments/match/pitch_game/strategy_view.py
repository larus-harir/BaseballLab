"""Read-only, reconciled report projections. Never repairs saved observations."""
from collections import Counter
from .strategy import new_stats

AREAS=tuple(h+'_'+v for v in ('high','middle','low') for h in ('inside','middle','outside'))


def heatmap(team,mode='selected',league=None,family=None):
    if mode not in ('selected','generated'):raise ValueError('Unknown heatmap provenance')
    bins=team.get('pitch_bins',{}).get(mode);counts=Counter();total=automatic=missing=0
    if bins is not None:
        for environment,families in bins.items():
            if league and environment.split(':')[0]!=league:continue
            for f,areas in families.items():
                if family and f!=family:continue
                for area,n in areas.items():
                    total+=n
                    if f=='unspecified':automatic+=n
                    elif area in AREAS:counts[area]+=n
                    else:missing+=n
        scope='joint'
    elif mode=='selected':
        if league:return {'available':False,'reason':'이전 기록에는 리그별 동시 집계가 없습니다.'}
        for action,n in team.get('defense',{}).items():
            if action=='pitch':
                if not family:total+=n;automatic+=n
            elif action.startswith('pitch:'):
                _,f,area,*_=action.split(':')
                if family and f!=family:continue
                total+=n
                if area in AREAS:counts[area]+=n
                else:missing+=n
        scope='legacy_selected_actions'
    else:
        if league or family:return {'available':False,'reason':'이전 기록의 생성 투구는 구종·리그별로 나눌 수 없습니다.'}
        for area,n in team.get('pitch_area',{}).items():
            total+=n
            if area in AREAS:counts[area]+=n
            else:missing+=n
        scope='legacy_generated_marginal'
    known=sum(counts.values())
    return {'available':True,'scope':scope,'total':total,'known':known,'unspecified':automatic,'missing':missing,
            'cells':{a:counts[a] for a in AREAS},'shares':{a:counts[a]/known if known else None for a in AREAS},
            'reconciled':total==known+automatic+missing}


def management(team,games,rules=None):
    changes=sum(team.get('defense',{}).get(k,0) for k in ('change_1','change_2'))
    measured=team.get('management',{});audited=bool(games and measured.get('games')==games)
    histogram=measured.get('histogram',{}) if audited else None
    consistent=(changes<=2*games and (not audited or measured.get('changes')==changes and sum(histogram.values())==games and
                sum(int(k)*n for k,n in histogram.items())==changes and not measured.get('invalid_changes')))
    return {'games':games,'changes':changes,'per_game':changes/games if games else None,
            'histogram':histogram,'audited':audited,'starter_checked':audited and rules=='pitcher-entry-after-appearance-v2','consistent':consistent,'roster_size':3,'max_changes_per_game':2}


def grouped_probabilities(values,role):
    result=Counter()
    for action,p in values.items():
        if role=='defense':
            if action.startswith('change_') or action=='intentional_walk':continue
            action='family:'+action.split(':')[1] if action.startswith('pitch:') else action
        result[action]+=p
    return dict(result)


def preference_changes(preferences,team,role):
    before=Counter();after=Counter();n=0
    for p in preferences:
        pair=p['teams'][team][role];n+=1
        before.update(grouped_probabilities(pair['before'],role));after.update(grouped_probabilities(pair['after'],role))
    if not n:return []
    return sorted([{'action':k,'before':before[k]/n,'after':after[k]/n,'delta':(after[k]-before[k])/n}
                   for k in before.keys()|after.keys()],key=lambda x:(-abs(x['delta']),x['action']))


def build(result):
    analysis=result.get('strategy_analysis',{});teams=analysis.get('teams',new_stats())
    games=sum(s['history'][-1]['games'] for s in result['seeds'] if s['history'])
    rows=[]
    for i,t in enumerate(teams):
        offense=t.get('offense',{});defense=t.get('defense',{});targets=t.get('targets',{})
        families=Counter()
        for k,n in defense.items():
            if k.startswith('pitch:'):families[k.split(':')[1]]+=n
        actual_pitches=sum(n for k,n in defense.items() if k=='pitch' or k.startswith('pitch:'))
        selected=heatmap(t);generated=heatmap(t,'generated')
        checks={'selected_pitch_count':selected['total']==actual_pitches,'generated_pitch_count':generated['total']==actual_pitches,
                'selected_partition':selected['reconciled'],'generated_partition':generated['reconciled'],
                'target_count':sum(targets.values())==sum(n for k,n in offense.items() if k.startswith('swing:')),
                'management':management(t,games,result.get('management_rules'))['consistent']}
        rows.append({'offense':offense,'targets':targets,'families':dict(families),'actual_pitches':actual_pitches,
            'unspecified_pitches':defense.get('pitch',0),'field':t.get('batted_area',{}),
            'changes':{role:preference_changes(analysis.get('preferences',[]),i,role) for role in ('offense','defense')},
            'management':management(t,games,result.get('management_rules')),'checks':checks})
    joint=all('pitch_bins' in t for t in teams)
    leagues=sorted({c['league'] for c in result['world']['cohorts']}) if joint else []
    maps={};family_keys=sorted(set().union(*(r['families'] for r in rows),*(t.get('pitch_family',{}) for t in teams)))
    for mode in ('selected','generated'):
        for league in [None,*leagues]:
            for family in [None,*family_keys]:
                if mode=='generated' and not joint and family:continue
                key='|'.join((mode,league or 'all',family or 'all'))
                maps[key]=[heatmap(t,mode,league,family) for t in teams]
    cohorts=[{k:c[k] for k in ('league','season')} for c in result['world']['cohorts']]
    # This projection omits repetitive raw counters, long hash lists and model
    # internals from the HTML. They remain unchanged in the saved research JSON.
    return {'schema':'strategy-report-view-v2','status':result['status'],'teams':rows,'games':games,
        'contexts':analysis.get('preferences',[]),'heatmaps':maps,'joint_pitch_bins':joint,'leagues':leagues,'families':family_keys,
        'growth':[{'seed':s['seed'],'history':[{'games':h['games'],'probes':h.get('strategy_probes',[])} for h in s['history']]} for s in result['seeds']],
        'runs':[{'seed':s['seed'],'replay':{k:v for k,v in (s.get('replay') or {}).items() if k in ('events','environment','management')}} for s in result['seeds']],
        'cohorts':cohorts,'experienced':sorted({k for s in result['seeds'] for k in s.get('training_environments',{})}),
        'evidence':{'holdout':result['world']['holdout_prediction']['test'],'asset_sha256':result['world']['asset_sha256'],
                    'contact_asset_sha256':result['world'].get('contact_asset_sha256'),'contact_coverage':result['world'].get('contact_coverage',{})}}
