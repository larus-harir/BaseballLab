from collections import Counter

import pytest

from baseball_lab.experiments.manager import season
from baseball_lab.experiments.manager.store import ManagerStore


def test_kbo_schedule_has_144_games_and_balanced_venues():
    dates=season.schedule(41)
    assert len(dates)==144
    venues=Counter(fixture for day in dates for fixture in day)
    assert len(venues)==90 and set(venues.values())=={8}
    assert all(len(day)==5 and {t for fixture in day for t in fixture}==set(season.TEAMS) for day in dates)


def test_draft_changes_probabilities_and_real_season_can_finish_after_a_reload(tmp_path):
    store=ManagerStore(tmp_path)
    view=store.change({'action':'create','team':'KIA','name':'연습 구단'})
    assert view['replaced']=='타이거즈'

    def change(action,**payload):
        nonlocal view
        view=store.change({'action':action,'id':view['id'],'revision':view['revision'],**payload})

    while view['draft']:
        candidate=view['choices'][0]
        training=next(iter(candidate['training']),None) if view['focus_used']==0 else None
        change('draft',player=candidate['id'],focus=training['id'] if training else '')
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
    slot=order[0];new=view['market'][slot][0]['id']
    change('transfer',slot=slot,player=new)
    assert view['roster'][slot]['id']==new and view['batting']==order and not view['market']
    store=ManagerStore(tmp_path)
    assert store.view(key)==view
    for expected in (60,90,120,144):
        change('advance')
        assert view['day']==expected
    assert len(view['results'])==144 and view['next']==0
    assert sum(r['games'] for r in view['standings'])==1440
    with pytest.raises(ValueError,match='끝났습니다'):
        change('advance')
    assert len(list((tmp_path/'outputs/manager').glob('*.json')))==1
