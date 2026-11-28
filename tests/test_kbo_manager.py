from collections import Counter
import json
from random import Random

import pytest

from baseball_lab.experiments.manager import postseason, presentation, season, skills
from baseball_lab.experiments.manager.store import ManagerStore


def test_kbo_schedule_has_144_games_and_balanced_venues():
    dates=season.schedule(41)
    assert len(dates)==144
    venues=Counter(fixture for day in dates for fixture in day)
    assert len(venues)==90 and set(venues.values())=={8}
    assert all(len(day)==5 and {t for fixture in day for t in fixture}==set(season.TEAMS) for day in dates)


def test_scouting_uses_stable_fictional_names_and_ordered_grades():
    profiles,_,_,pools,_=season.league()
    names=presentation.names(41)
    assert len(set(names.values()))==len(profiles)
    assert not set(names.values()) & {p['name'] for p in profiles.values()}
    assert presentation.names(42)!=names
    for role,trait in (('pitcher','control'),('batter','power')):
        candidates=[profiles[key] for key in pools[role]]
        candidates.sort(key=lambda p:presentation.trait_score(trait,p,p['rates']))
        assert presentation.grade(trait,candidates[0],candidates[0]['rates'])=='D'
        assert presentation.grade(trait,candidates[-1],candidates[-1]['rates'])=='S'
        for profile in candidates:
            _,options=presentation.scouting(profile,'')
            for option in options:
                assert 'SABCD'.index(option['after'])<='SABCD'.index(option['before'])


def test_wild_card_advantage_and_korean_series_home_order():
    ladder={'seeds':list(season.TEAMS)[:5],'rounds':[],'champion':None}
    wildcard=postseason.next_series(ladder)
    away,home=postseason.current_teams(wildcard)
    assert (away,home)==tuple(reversed(ladder['seeds'][3:5]))
    postseason.finish_game(wildcard,{'away':away,'home':home,'a':3,'h':2})
    assert wildcard['winner'] is None
    postseason.finish_game(wildcard,{'away':away,'home':home,'a':1,'h':1})
    assert wildcard['winner']==home
    wildcard=postseason.next_series(ladder)
    for _ in range(2):postseason.finish_game(wildcard,{'away':away,'home':home,'a':3,'h':2})
    assert wildcard['winner']==away
    final={'stage':3,'high':home,'low':away,'games':[]}
    for host in (home,home,away,away,away,home,home):
        assert postseason.current_teams(final)[1]==host
        final['games'].append({'home':host,'a':2,'h':2 if len(final['games'])==2 else 1})
    assert postseason.current_teams(final)[1]==away  # Replay at the drawn game's venue.


def test_postseason_skips_cpu_rounds_and_stops_after_one_user_game(monkeypatch):
    teams=list(season.TEAMS)[:5]
    bracket={'seeds':teams,'rounds':[],'champion':None,'stats':{}}
    monkeypatch.setattr(season,'play',lambda *args,**kwargs:(1,3))
    rosters={team:None for team in teams}
    mine=teams[1]
    postseason.play_to_next_user_game(bracket,rosters,41,mine,None)
    assert [r['winner'] for r in bracket['rounds']]==[teams[3],teams[2]]
    assert postseason.next_series(bracket)['high']==mine
    postseason.play_to_next_user_game(bracket,rosters,41,mine,None,play_user=True)
    assert len(bracket['rounds'][-1]['games'])==1
    assert bracket['champion'] is None
    postseason.play_to_next_user_game(bracket,rosters,41,'no-user-team',None)
    assert bracket['champion']==teams[0]


def test_fielding_and_speed_change_only_eligible_plays():
    event,net=skills.field_contact('single',1.,.5,Random(31))
    assert (event,net)==('other',1)
    assert skills.field_contact('other',0.,.5,Random(31))==('single',-1)
    for event in ('home_run','strikeout','walk','double','triple','hbp'):
        assert skills.field_contact(event,1.,.5,Random(31))==(event,0)
    world=season.movement_world()
    slow=Random(42);fast=Random(42)
    count=lambda rating,rng:sum(skills.advance(world,0,1,'single',rating,rng)==(0,5,0) for _ in range(1000))
    assert count(1.,fast)>count(0.,slow)
    assert skills.advance(world,0,0,'single',1.,Random(41))==world.advance(0,0,'single',Random(41))
    assert skills.run_expectancy()[0]>skills.run_expectancy()[8]>skills.run_expectancy()[16]>0


def test_draft_changes_probabilities_and_real_season_can_finish_after_a_reload(tmp_path):
    store=ManagerStore(tmp_path)
    view=store.change({'action':'create','team':'KIA','name':'연습 구단'})
    assert view['replaced']=='타이거즈'

    def change(action,**payload):
        nonlocal view
        view=store.change({'action':action,'id':view['id'],'revision':view['revision'],**payload})

    while view['draft']:
        candidate=view['choices'][0]
        slot=view['draft']
        training=next(iter(candidate['training']),None) if view['focus_used']==0 else None
        change('draft',player=candidate['id'],focus=training['id'] if training else '')
        assert view['roster'][slot]['name']==candidate['name']
        assert 'rates' not in candidate and all(a['grade'] in 'SABCD' for a in candidate['abilities'])
    assert len(view['roster'])==16 and len({p['id'] for p in view['roster'].values()})==16
    assert view['focus_used']==1
    p=next(p for p in view['roster'].values() if p['focus'])
    profile=season.league()[0][p['id']]
    before=profile['rates'];after=season.adjusted(profile,p['focus'])
    assert before!=after and sum(after.values())==pytest.approx(1.)
    key=view['id'];revision=view['revision']
    change('advance')
    assert view['day']==30 and len(view['market'])==16
    assert len(view['standings'])==10 and {r['games'] for r in view['standings']}=={30}
    assert {r['name'] for r in view['standings']}==(set(season.TEAMS.values())-{'타이거즈'})|{'연습 구단'}
    assert sum(r['w'] for r in view['standings'])==sum(r['l'] for r in view['standings'])
    assert sum(p['stats']['n'] for p in view['roster'].values() if p['role']=='batter')>100
    with pytest.raises(ValueError,match='새로고침'):
        store.change({'action':'advance','id':key,'revision':revision})
    order=list(reversed(view['batting']))
    change('lineup',batting=order,rotation=view['rotation'])
    slot=order[0];new=view['market'][slot][0]['id'];released=view['roster'][slot]['id']
    change('transfer',slot=slot,player=new)
    assert view['roster'][slot]['id']==new and view['batting']==order and not view['market']
    # Existing season files used serial numbers as display names.
    file=tmp_path/'outputs'/'manager'/f'{key}.json'
    archived=json.loads(file.read_text(encoding='utf-8'))
    archived['names']={key:f'신인 {i:02d}' for i,key in enumerate(archived['names'],1)}
    file.write_text(json.dumps(archived),encoding='utf-8')
    store=ManagerStore(tmp_path)
    assert store.view(key)==view
    for expected in (60,90,120,144):
        change('advance')
        assert view['day']==expected
    assert len(view['results'])==144 and view['next']==0
    assert sum(r['games'] for r in view['standings'])==1440
    for game in view['results']:
        scored,allowed=(1,0) if game['home'] else (0,1)
        assert sum((inning[scored] or 0) for inning in game['innings'])==game['scored']
        assert sum((inning[allowed] or 0) for inning in game['innings'])==game['allowed']
    with pytest.raises(ValueError,match='끝났습니다'):
        change('advance')
    regular=view['standings']
    seeds=view['postseason']['seeds']
    for _ in range(50):
        upcoming=view['postseason']['next']
        if not upcoming:break
        assert view['team'] in upcoming['teams']
        previous=sum(len(series['games']) for series in view['postseason']['rounds']
                     if view['team'] in (series['high'],series['low']))
        change('playoff')
        played=sum(len(series['games']) for series in view['postseason']['rounds']
                   if view['team'] in (series['high'],series['low']))
        assert played==previous+1
    ps=view['postseason']
    assert ps['champion'] in seeds and not ps['next']
    assert [round['name'] for round in ps['rounds']]==['와일드카드','준플레이오프','플레이오프','한국시리즈']
    assert ps['rounds'][-1]['winner']==ps['champion'] and 4 in ps['rounds'][-1]['wins']
    assert all(new['low']==old['winner'] for old,new in zip(ps['rounds'],ps['rounds'][1:]))
    recap=view['season_report']
    assert released in {player['id'] for player in recap['players']}
    assert sum(player['stats']['n'] for player in recap['players'])>0
    assert recap['awards']['mvp']['team'] in season.TEAMS
    gloves=recap['awards']['gloves']
    assert gloves and len({g['slot'] for g in gloves})==len(gloves) and all(g['value']>0 for g in gloves)
    assert view['standings']==regular and store.view(key)==view
    assert len(list((tmp_path/'outputs/manager').glob('*.json')))==1

    fresh=store.change({'action':'create','team':view['team'],'name':view['name']})
    other=store.change({'action':'quick_draft','id':fresh['id'],'revision':fresh['revision']})
    assert other['id']!=key and other['day']==0 and len(other['roster'])==16 and other['draft'] is None
    assert store.view(key)==view
    # Old saves can open a recap without introducing awards for unrecorded rivals.
    archived=json.loads(file.read_text(encoding='utf-8'))
    del archived['league_stats'],archived['player_slots']
    file.write_text(json.dumps(archived),encoding='utf-8')
    assert store.view(key)['season_report']['awards'] is None
