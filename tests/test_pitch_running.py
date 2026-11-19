"""MOCK_TEST_ONLY: joint pitch/steal semantics and bunt rules."""
from random import Random
from collections import Counter,defaultdict
from baseball_lab.data.pitch_actions import running_play
from baseball_lab.experiments.match.pitch_game.research import World,Observation,checked_sequence,play


def source(event='SB2',caught=False):
    return {'gid':'MOCK_TEST_ONLY_200004010','inning':'1','vis_home':'0','pa':'0',
        'event':event,'pitches':'>C','count':'00','outs_pre':'1','outs_post':'2' if caught else '1',
        'br1_pre':'MOCK_TEST_ONLY_runner','br2_pre':'','br3_pre':'',
        'br1_post':'','br2_post':'' if caught else 'MOCK_TEST_ONLY_runner','br3_post':'','runs':'0'}


def test_isolated_steal_keeps_pitch_count_and_success_and_failure():
    success=running_play(source(),1)
    caught=running_play(source('CS2(26)',True),2)
    assert success['action']==caught['action']=='steal_2'
    assert success['pitch_event']==caught['pitch_event']=='strike'
    assert (success['balls'],success['strikes'],success['outs_added'],success['end_bases'])==(0,0,0,2)
    assert (caught['outs_added'],caught['end_bases'])==(1,0)
    for change in ({'pitches':'>S'},{'count':'02'},{'count':'30'},
                   {'event':'SB3;SB2'},{'wp':'1'},{'event':'CS2(2E6)'},{'pa':'1'}):
        assert running_play({**source(),**change},1) is None


def test_bunt_foul_with_two_strikes_finishes_as_strikeout():
    row={'intentional_walk':False,'pitches':'CLL','event':'strikeout'}
    seq,reason=checked_sequence(row)
    assert reason is None
    assert seq[-1]==(0,2,'bunt','bunt_foul')
    assert checked_sequence({**row,'pitches':'CLX','event':'single','bunt_contact':True})[0][-1][2]=='bunt'
    # A failed bunt does not turn later ordinary contact into a bunt.
    assert checked_sequence({**row,'pitches':'LX','event':'single','bunt_contact':False})[0][-1][2]=='swing'


def test_legal_actions_depend_on_fit_support_and_joint_draw_retains_count():
    world=World.__new__(World)
    world.baseline=defaultdict(Counter);world.supported={'bunt':{'bunt_foul','out'}}
    world.runner=defaultdict(Counter);world.running=defaultdict(Counter)
    o=Observation(1,0,1,1,0,0,0,0,0)
    assert world.legal(o)==('take','swing')
    world.baseline[0,0,'bunt']['out']=10
    # Bunts cannot borrow ordinary swing runner movements.
    world.runner[1,1,'out',False][1,1,0]=100
    assert 'bunt' not in world.legal(o)
    world.runner[1,1,'out',True][1,2,0]=10
    world.running[1,1,0,0,'steal_2'][('strike',0,2)]=8
    world.running[1,1,0,0,'steal_2'][('ball',1,0)]=2
    assert world.legal(o)==('take','swing','bunt','steal_2')
    draws={world.run(o,'steal_2',Random(i)) for i in range(100)}
    assert draws=={('strike',0,2),('ball',1,0)}


def test_game_running_pitch_keeps_count_and_out_without_ending_the_pa():
    class First:
        def act(self,o,legal,rng):return legal[0]
    class JointWorld:
        pitchers=['MOCK_TEST_ONLY_0','MOCK_TEST_ONLY_1','MOCK_TEST_ONLY_2']
        def legal(self,o):
            self.current=o
            return ('steal_2',) if o.bases==1 and o.balls==o.strikes==0 else ('swing',)
        def pitch(self,*args):
            o=self.current
            if o.inning==9 and o.bottom:return 'home_run'
            return 'single' if o.outs==0 and o.bases==0 and o.balls==o.strikes==0 else 'strike'
        def run(self,o,action,rng):return 'ball',1,0
        def advance(self,outs,bases,event,rng):
            if event=='single':return outs,1,0
            if event=='home_run':return outs,0,1+bases.bit_count()
            assert event=='strikeout'
            return outs+1,bases if outs<2 else 0,0
    game=play(JointWorld(),[(First(),First()),(First(),First())],41,record=True)
    attempts=[i for i,e in enumerate(game['events']) if e['offense']=='steal_2']
    assert attempts
    i=attempts[0];event=game['events'][i];nxt=game['events'][i+1]
    assert event['running_outs']==1 and event['after_outs']==1 and event['after_bases']==0
    assert nxt['balls']==1 and nxt['strikes']==0 and nxt['outs']==1
    assert game['winner']==1 and game['scores']==[0,1]
