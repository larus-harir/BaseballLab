"""KBO season scheduling and evidence-based plate appearance simulation."""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from random import Random

from baseball_lab.data.compact import index, players
from baseball_lab.matchup.event_schema import partition
from baseball_lab.matchup.models import generalized_log5

YEAR = 2026
GAMES = 144
BLOCK = 30
MAX_INNINGS = 11
TEAMS = {
    'KIA':'타이거즈', 'LG':'트윈스', '두산':'베어스', '롯데':'자이언츠', '삼성':'라이온즈',
    '한화':'이글스', 'SSG':'랜더스', 'NC':'다이노스', 'KT':'위즈', '키움':'히어로즈',
}
POSITIONS = ('포수', '1루수', '2루수', '3루수', '유격수', '좌익수', '중견수', '우익수', '지명타자')
SLOTS = (*POSITIONS, *(f'선발 {i}' for i in range(1,6)), '중간계투', '마무리')
TRAINING = {'batter':{'contact':('hit_other',1,'컨택'), 'eye':('walk',1,'선구안'), 'power':('home_run',1,'장타력')},
            'pitcher':{'control':('walk',-1,'제구'), 'stuff':('strikeout',1,'탈삼진'), 'limit':('home_run',-1,'피홈런 억제')}}
FIELDS = ('HBP', 'HR')


def schedule(seed):
    ring=list(TEAMS)
    rng=Random(seed)
    rng.shuffle(ring)
    rounds=[]
    for turn in range(len(ring)-1):
        rounds.append([(b,a) if (turn+i)%2 else (a,b)
                       for i,(a,b) in enumerate(zip(ring[:5],reversed(ring[5:])))])
        ring=[ring[0],ring[-1],*ring[1:-1]]
    # Sixteen games per opponent, eight at each venue.
    return [rounds[day] if cycle%2==0 else [(b,a) for a,b in rounds[day]]
            for cycle in range(16) for day in range(len(rounds))]


@lru_cache(maxsize=1)
def league():
    profiles={}
    teams={team:{'batter':[], 'pitcher':[]} for team in TEAMS}
    for row in players():
        if row['league']!='KBO' or row['season']!=YEAR or row['source_namespace']!='kaggle-netsong-kbo':
            continue
        role=row['role'];team=row['source_fields']['team_label']
        if team not in teams or role not in ('batter','pitcher'):
            continue
        counts=row['counts']
        try:
            events=partition(counts,role,FIELDS)
        except ValueError:
            continue
        if role=='batter' and any(type(counts[key]) is not int for key in ('2B','3B')):
            continue
        n=sum(events.values());games=counts['G'] or 0
        key=row['entity_id']
        profile={'id':key,'name':row['source_fields']['Name'],'role':role,'team':team,'n':n,'events':events,
                 'games':games,'ip_per_game':(counts['IP_OUTS'] or 0)/max(1,games)}
        if role=='batter':
            singles=events['hit_other']-counts['2B']-counts['3B']
            if singles<0:
                continue
            profile['hit_mix']=(singles,counts['2B'],counts['3B'])
            sb,cs=counts['SB'],counts['CS']
            profile['steal_attempt_rate']=(sb+cs)/n if n and sb is not None and cs is not None else None
        profiles[key]=profile
        teams[team][role].append(key)
    total=Counter()
    for p in profiles.values():
        if p['role']=='batter':total.update(p['events'])
    reference={event:n/sum(total.values()) for event,n in total.items()}
    hit_mix=tuple(sum(p['hit_mix'][i] for p in profiles.values() if p['role']=='batter') for i in range(3))
    runners=[p for p in profiles.values() if p.get('steal_attempt_rate') is not None]
    attempt_prior=sum(p['steal_attempt_rate']*p['n'] for p in runners)/sum(p['n'] for p in runners) if runners else 0.
    for p in profiles.values():
        # Same relative-rate inputs and 100 PA shrinkage as the matchup screen.
        p['rates']={k:(p['events'][k]+100*prior)/(p['n']+100) for k,prior in reference.items()}
        if p['role']=='batter' and not sum(p['hit_mix']):p['hit_mix']=hit_mix
        if p.get('steal_attempt_rate') is not None:
            p['steal_attempt_rate']=(p['steal_attempt_rate']*p['n']+100*attempt_prior)/(p['n']+100)
    pools={role:sorted(p['id'] for p in profiles.values() if p['role']==role and p['n']>=100) for role in TRAINING}
    benchmarks={}
    for role,choices in TRAINING.items():
        for focus,(event,sign,_) in choices.items():
            values=sorted(sign*profiles[key]['rates'][event] for key in pools[role])
            benchmarks[focus]=sign*values[3*(len(values)-1)//4]
    for roster in teams.values():
        roster['batter'].sort(key=lambda k:(-profiles[k]['n'],k))
        starters=sorted(roster['pitcher'],key=lambda k:(-(profiles[k]['n']>=100),-profiles[k]['ip_per_game'],k))[:5]
        relief=sorted(set(roster['pitcher'])-set(starters),key=lambda k:(-profiles[k]['games'],k))[:2]
        roster['batter']=roster['batter'][:9]
        roster['pitcher']=starters+relief
        if len(roster['batter'])!=9 or len(roster['pitcher'])!=7:
            raise ValueError('10개 팀의 시즌 명단이 충분하지 않습니다.')
    return profiles,teams,reference,pools,benchmarks


def role_for(slot):
    return 'batter' if slot in POSITIONS else 'pitcher'


def candidates(seed,block,slot,excluded):
    pools=league()[3]
    available=[key for key in pools[role_for(slot)] if key not in excluded]
    return Random(f'{seed}:{block}:{slot}').sample(available,3)


def adjusted(profile,focus):
    rates=profile['rates']
    if not focus:return rates
    event,sign,_=TRAINING[profile['role']][focus]
    current=rates[event];target=league()[4][focus]
    # Game development choice: move a quarter of the way toward the observed
    # upper quartile on one skill. Rescale remaining outcomes, including outs.
    if sign*(target-current)<=0:return rates
    new=current+(target-current)/4
    return {k:new if k==event else v*(1-new)/(1-current) for k,v in rates.items()}


@lru_cache(maxsize=1)
def movement_world():
    from baseball_lab.experiments.match.pitch_game.modern_world import ModernWorld
    world=ModernWorld(['KBO'],[YEAR])
    world.begin_game(0)
    return world


def play(away,home,seed,day,cache,player_stats,*,max_innings=MAX_INNINGS,innings=None,fielding=None,accounts=None):
    from . import skills

    profiles,_,reference,_,_=league()
    world=movement_world()
    rng=Random(seed);scores=[0,0];positions=[0,0]
    teams=(away,home)
    if accounts is None:accounts=tuple(player_stats if roster[3] else None for roster in teams)
    speed=skills.running_ratings() if fielding is not None else {}
    expectancy=skills.run_expectancy() if fielding is not None else None
    for inning in range(1,max_innings+1):
        frame=[0,None]
        if innings is not None:innings.append(frame)
        for offense in (0,1):
            defense=1-offense
            if offense==1 and inning>=9 and scores[1]>scores[0]:return tuple(scores)
            frame[offense]=0
            batters,_,focuses,_,_=teams[offense]
            _,opponents,op_focus,_,fielders=teams[defense]
            hit_account,pitch_account=accounts[offense],accounts[defense]
            # Five-start rotation and a fixed bullpen handoff in this version.
            pitcher=opponents[(day-1)%5 if inning<=5 else 5 if inning<=7 else 6]
            outs=bases=0;runner=None
            for _ in range(100):
                hitter=batters[positions[offense]]
                positions[offense]=(positions[offense]+1)%9
                pair=(hitter,pitcher,focuses.get(hitter),op_focus.get(pitcher))
                if pair not in cache:
                    q,_,_=generalized_log5(adjusted(profiles[hitter],pair[2]),adjusted(profiles[pitcher],pair[3]),reference)
                    mix=profiles[hitter]['hit_mix']
                    single_to_out=q['hit_other']*mix[0]/sum(mix)/q['other']
                    cache[pair]=(tuple(q),tuple(q.values()),single_to_out)
                events,weights,single_to_out=cache[pair]
                event=rng.choices(events,weights=weights,k=1)[0]
                if event=='hit_other':
                    event=rng.choices(('single','double','triple'),weights=profiles[hitter]['hit_mix'],k=1)[0]
                if fielding is not None and event in ('single','other'):
                    fielder=rng.choice(fielders)
                    event,saved=skills.field_contact(event,fielding[fielder],single_to_out,rng)
                    if pitch_account is not None:
                        record_fielding(pitch_account,fielder,saved)
                start=outs*8+bases
                terminal='out' if event=='other' else event
                if fielding is None:
                    outs,bases,runs=world.advance(outs,bases,terminal,rng)
                else:
                    outs,bases,runs=skills.advance(world,outs,bases,terminal,speed.get(runner),rng)
                    runner=first_base_runner(event,outs,bases,hitter,runner,start % 8)
                if offense==1 and inning>=9 and event!='home_run':
                    runs=min(runs,max(0,scores[0]-scores[1]+1))
                value=runs+expectancy[min(24,outs*8+bases)]-expectancy[start] if expectancy is not None else None
                if hit_account is not None:record_pa(hit_account,hitter,event,value)
                if pitch_account is not None:record_pa(pitch_account,pitcher,event,-value if value is not None else None)
                scores[offense]+=runs
                frame[offense]+=runs
                if offense==1 and inning>=9 and scores[1]>scores[0]:return tuple(scores)
                if outs==3:break
            else:raise ValueError('한 이닝의 진행 한도에 도달했습니다. 이번 구간은 저장하지 않았습니다.')
        if inning>=9 and scores[0]!=scores[1]:break
    return tuple(scores)


def first_base_runner(event,outs,bases,hitter,runner,previous_bases):
    if outs==3 or not bases&1:return None
    if event in ('single','walk','hbp'):return hitter
    return runner if event=='strikeout' and bases==previous_bases else None


def record_fielding(records,player,saved):
    stats=records.setdefault(player,{})
    stats['field_chances']=stats.get('field_chances',0)+1
    stats['field_net']=stats.get('field_net',0)+saved


def record_pa(records,player,event,value):
    stats=records.setdefault(player,{})
    stats['n']=stats.get('n',0)+1
    stats[event]=stats.get(event,0)+1
    if value is not None:stats['value']=stats.get('value',0.)+value


def record(standings,away,home,a,h):
    for team,for_runs,against in ((away,a,h),(home,h,a)):
        line=standings[team]
        line['w' if for_runs>against else 'l' if for_runs<against else 'd']+=1
        line['rf']+=for_runs;line['ra']+=against


def win_rate(line):
    return Fraction(line['w'],line['w']+line['l']) if line['w']+line['l'] else Fraction(0)


def table(standings):
    result=[];last=None;rank=0
    for team,line in sorted(standings.items(),key=lambda item:(-win_rate(item[1]),TEAMS[item[0]])):
        rate=win_rate(line)
        if rate!=last:rank=len(result)+1
        last=rate
        result.append({'team':team,'name':TEAMS[team],'rank':rank,'pct':float(rate),
                       'games':line['w']+line['l']+line['d'],**line})
    return result


def source_signature():
    try:
        from baseball_lab.experiments.match.pitch_game.modern_world import ASSET_SHA256
    except ModuleNotFoundError as error:
        if error.name != 'numpy':
            raise
        raise ValueError('감독 모드에는 학습 의존성이 필요합니다. python -m pip install -e ".[learning]" 실행 후 다시 열어 주세요.') from error
    return [index()['players_sha256'],ASSET_SHA256]
