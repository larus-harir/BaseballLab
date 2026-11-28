"""Local saved seasons and validated game actions."""
from collections import Counter
import json
from pathlib import Path
from random import Random
import re
import secrets
from threading import RLock

from baseball_lab.data.lineage import write_json
from baseball_lab.data.protection import private
from . import presentation,season

FOCUS_LIMIT=3
FORMAT='kbo-manager-season-v1'


class ManagerStore:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.directory=self.root/'outputs'/'manager'
        self.lock=RLock()

    def _file(self,session):
        if not isinstance(session,str) or not re.fullmatch('[0-9a-f]{24}',session):
            raise ValueError('시즌 주소가 올바르지 않습니다.')
        path=self.directory/f'{session}.json'
        if self.directory.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('시즌 저장 위치를 확인하세요.')
        return path

    def _read(self,session):
        file=self._file(session)
        if not file.is_file():raise ValueError('저장된 시즌을 찾을 수 없습니다.')
        state=json.loads(file.read_text(encoding='utf-8'))
        if state['schema']!=FORMAT or state['sources']!=season.source_signature():
            raise ValueError('이 시즌을 만든 자료 또는 모형 버전이 다릅니다.')
        return state

    def view(self,session=None):
        if session is None:
            return {'year':season.YEAR,'teams':season.TEAMS,'games':season.GAMES,'block':season.BLOCK}
        with self.lock:return visible(self._read(session))

    def change(self,request):
        if not isinstance(request,dict):raise ValueError('시즌 요청을 확인하세요.')
        action=request.get('action')
        with self.lock:
            if action=='create':
                team=request.get('team');name=request.get('name','')
                if not isinstance(team,str) or team not in season.TEAMS:
                    raise ValueError('대신할 팀을 선택하세요.')
                if not isinstance(name,str) or not 1<=len(name.strip())<=18 or not name.isprintable():
                    raise ValueError('팀 이름은 1~18자로 입력하세요.')
                state=new_season(team,name.strip())
            else:
                state=self._read(request.get('id'))
                supplied=request.get('revision')
                if type(supplied) is not int or supplied!=state['revision']:
                    raise ValueError('다른 화면에서 시즌이 바뀌었습니다. 새로고침하세요.')
                apply(state,action,request)
            state['revision']+=1
            view=visible(state)
            file=self._file(state['id'])
            private(self.directory,directory=True)
            write_json(file,state,compact=True)
            return view


def new_season(team,name):
    return {'schema':FORMAT,'sources':season.source_signature(),'id':secrets.token_hex(12),
            'seed':secrets.randbits(64),'revision':0,'team':team,'name':name,'day':0,'roster':{},
            'batting':list(season.POSITIONS),'rotation':list(season.SLOTS[9:14]),'focus':{},'names':{},
            'standings':{key:dict(w=0,d=0,l=0,rf=0,ra=0) for key in season.TEAMS},
            'stats':{},'results':[],'event':None,'transfer':False}


def choices(state,slot):
    return season.candidates(state['seed'],state['day'],slot,state['names'])


def card(state,key):
    profile=season.league()[0][key]
    focus=state['focus'].get(key,'')
    abilities,training=presentation.scouting(profile,focus)
    stats=state['stats'].get(key,{})
    hits=sum(stats.get(e,0) for e in ('single','double','triple','home_run'))
    return {'id':key,'name':presentation.names(state['seed'])[key],'role':profile['role'],
            'abilities':abilities,'training':training,'focus':focus,
            'stats':{'n':stats.get('n',0),'hits':hits,'hr':stats.get('home_run',0),
                     'bb':stats.get('walk',0),'so':stats.get('strikeout',0)}}


def visible(state):
    roster=state['roster']
    slot=next((slot for slot in season.SLOTS if slot not in roster),None)
    can_transfer=bool(state['event']) and not state['transfer'] and state['day']<season.GAMES
    standings=season.table(state['standings'])
    for row in standings:
        if row['team']==state['team']:row['name']=state['name']
    return {'id':state['id'],'revision':state['revision'],'name':state['name'],'team':state['team'],
            'replaced':season.TEAMS[state['team']],'day':state['day'],'games':season.GAMES,'year':season.YEAR,
            'next':min(season.BLOCK,season.GAMES-state['day']),'focus_limit':FOCUS_LIMIT,'focus_used':len(state['focus']),
            'slots':season.SLOTS,'batting':state['batting'],'rotation':state['rotation'],
            'roster':{s:card(state,k) for s,k in roster.items()},'draft':slot,
            'choices':[card(state,key) for key in choices(state,slot)] if slot else [],
            'market':{s:[card(state,k) for k in choices(state,s)] for s in season.SLOTS} if can_transfer else {},
            'standings':standings,'event':state['event'],'results':state['results']}


def pick(state,slot,key,focus):
    if not isinstance(key,str) or key not in choices(state,slot):
        raise ValueError('이번에 제시된 선수 중 한 명을 선택하세요.')
    previous=state['roster'].get(slot)
    state['focus'].pop(previous,None)
    set_focus(state,key,focus)
    state['roster'][slot]=key
    state['names'][key]=presentation.names(state['seed'])[key]


def set_focus(state,key,focus):
    if not isinstance(focus,str):raise ValueError('훈련 항목을 선택하세요.')
    if not focus:
        state['focus'].pop(key,None)
        return
    if focus not in {item['id'] for item in card(state,key)['training']}:
        raise ValueError('이 선수에게 적용할 수 있는 훈련을 고르세요.')
    if key not in state['focus'] and len(state['focus'])>=FOCUS_LIMIT:
        raise ValueError('집중 훈련은 세 명까지 지정할 수 있습니다.')
    state['focus'][key]=focus


def apply(state,action,request):
    if state['day']==season.GAMES:raise ValueError('시즌이 끝났습니다.')
    roster=state['roster']
    slot=next((s for s in season.SLOTS if s not in roster),None)
    if action=='draft' and slot:
        pick(state,slot,request.get('player'),request.get('focus',''))
        return
    if slot:raise ValueError('선수 선발을 마쳐 주세요.')
    if action=='lineup':
        for key,required in (('batting',season.POSITIONS),('rotation',season.SLOTS[9:14])):
            order=request.get(key)
            if not isinstance(order,list) or not all(isinstance(x,str) for x in order) or Counter(order)!=Counter(required):
                raise ValueError('타순 또는 선발 순서에 빠지거나 중복된 자리가 있습니다.')
            state[key]=order
    elif action=='focus':
        key=request.get('player')
        if key not in roster.values():raise ValueError('현재 명단에서 선수를 선택하세요.')
        set_focus(state,key,request.get('focus',''))
    elif action=='transfer':
        slot=request.get('slot')
        if not isinstance(slot,str) or not state['event'] or state['transfer'] or slot not in roster:
            raise ValueError('중간 점검마다 한 자리만 선수 교체가 가능합니다.')
        pick(state,slot,request.get('player'),request.get('focus',''))
        state['transfer']=True
    elif action=='advance':advance(state)
    else:raise ValueError('현재 할 수 있는 작업을 선택하세요.')


def advance(state):
    _,teams,_,_,_=season.league()
    rosters={k:(v['batter'],v['pitcher'],{},False) for k,v in teams.items()}
    mine=state['team'];roster=state['roster']
    rosters[mine]=([roster[s] for s in state['batting']],
                   [roster[s] for s in (*state['rotation'],*season.SLOTS[14:])],state['focus'],True)
    start=state['day'];end=min(start+season.BLOCK,season.GAMES)
    prior_runs=sum(row['rf'] for row in state['standings'].values())
    fixtures=season.schedule(state['seed']);cache={};recent=[]
    for day in range(start+1,end+1):
        for away,home in fixtures[day-1]:
            seed=f'{state["seed"]}:{day}:{away}:{home}'
            a,h=season.play(rosters[away],rosters[home],seed,day,cache,state['stats'])
            season.record(state['standings'],away,home,a,h)
            if mine in (away,home):
                entry={'day':day,'opponent':season.TEAMS[away if home==mine else home],
                       'home':home==mine,'scored':h if home==mine else a,'allowed':a if home==mine else h}
                recent.append(entry)
    state['day']=end;state['results'].extend(recent)
    w=sum(g['scored']>g['allowed'] for g in recent);l=sum(g['scored']<g['allowed'] for g in recent)
    runs=sum(g['scored'] for g in recent);allowed=sum(g['allowed'] for g in recent)
    average=(sum(row['rf'] for row in state['standings'].values())-prior_runs)/len(season.TEAMS)
    if end==season.GAMES:title='정규시즌 종료'
    elif runs<average and average-runs>=allowed-average:title='타선 점검'
    elif allowed>average:title='투수진 점검'
    else:title='전력 점검'
    state['event']={'from':start+1,'to':end,'w':w,'l':l,'d':len(recent)-w-l,'rf':runs,'ra':allowed,
                    'league_runs':round(average,1),'title':title}
    state['transfer']=False
