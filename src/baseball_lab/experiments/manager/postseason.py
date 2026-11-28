"""Five-team KBO postseason ladder for the local manager game."""
from copy import deepcopy
from random import Random

from . import season

# Home games for the higher seed come first in each schedule.
ROUNDS = (
    ('와일드카드', 4, 1, (True, True)),
    ('준플레이오프', 3, 3, (True, True, False, False, True)),
    ('플레이오프', 2, 3, (True, True, False, False, True)),
    ('한국시리즈', 1, 4, (True, True, False, False, False, True, True)),
)
MAX_INNINGS = 15


def start(standings, seed):
    teams=list(standings)
    # Stable game tiebreak also works for seasons saved before this mode.
    Random(f'{seed}:postseason-seeding').shuffle(teams)
    teams.sort(key=lambda team:(season.win_rate(standings[team]),
                                standings[team]['rf']-standings[team]['ra'],standings[team]['rf']),reverse=True)
    return {'seeds':teams[:5],'rounds':[],'champion':None,'stats':{}}


def next_series(bracket):
    if bracket['champion']:
        return None
    rounds=bracket['rounds']
    if rounds and not rounds[-1]['winner']:
        return rounds[-1]
    stage=len(rounds)
    name,seed,target,_=ROUNDS[stage]
    lower=bracket['seeds'][4] if stage==0 else rounds[-1]['winner']
    return {'stage':stage,'name':name,'high':bracket['seeds'][seed-1],'low':lower,
            'target':target,'wins':[0,0],'games':[],'winner':None}


def current_teams(series):
    stage=series['stage']
    hosts=ROUNDS[stage][3]
    index=len(series['games'])
    high,low=series['high'],series['low']
    if index<len(hosts):
        high_home=hosts[index]
    else:
        # Tied games are replayed at the same venue after the planned dates.
        draws=[g['home'] for g in series['games'] if g['a']==g['h']]
        high_home=draws[index-len(hosts)]==high
    return (low,high) if high_home else (high,low)


def finish_game(series,game):
    series['games'].append(game)
    if game['a']==game['h']:
        if series['stage']==0:series['winner']=series['high']
        return
    winner=game['away'] if game['a']>game['h'] else game['home']
    index=0 if winner==series['high'] else 1
    series['wins'][index]+=1
    target=2 if series['stage']==0 and index==1 else series['target']
    if series['wins'][index]>=target:
        series['winner']=winner


def advance(bracket,rosters,seed):
    series=next_series(bracket)
    if series is None:raise ValueError('포스트시즌이 끝났습니다.')
    if not bracket['rounds'] or bracket['rounds'][-1] is not series:
        bracket['rounds'].append(series)
    away,home=current_teams(series)
    number=len(series['games'])+1
    game_seed=f'{seed}:postseason:{series["stage"]}:{number}'
    day=1+sum(len(r['games']) for r in bracket['rounds'])
    innings=[]
    a,h=season.play(rosters[away],rosters[home],game_seed,day,{},bracket['stats'],max_innings=MAX_INNINGS,innings=innings)
    finish_game(series,{'number':number,'away':away,'home':home,'a':a,'h':h,'innings':innings})
    if series['stage']==len(ROUNDS)-1 and series['winner']:
        bracket['champion']=series['winner']


def view(bracket,team):
    current=next_series(bracket)
    active=team in bracket['seeds'] and all(r['winner'] in (None,team) for r in bracket['rounds']
                                            if team in (r['high'],r['low']))
    rounds=deepcopy(bracket['rounds'])
    if current and (not rounds or rounds[-1]['stage']!=current['stage']):rounds.append(deepcopy(current))
    return {'seeds':bracket['seeds'],'rounds':rounds,'champion':bracket['champion'],
            'active':active,'next':{'stage':current['stage'],'name':current['name'],
                                   'number':len(current['games'])+1,'teams':current_teams(current)} if current else None}
