"""MOCK_TEST_ONLY saved-event explanations; no training or data collection."""
from copy import deepcopy
from baseball_lab.experiments.match.full_game.results import explain,render


def result(home=True):
    # Two deliberately explicit scenes, no inference from scores into hit types.
    events=[{'inning':1,'bottom':0,'before':{'outs':0,'bases':1},'after':{'outs':1,'bases':0},'offense':'ordinary_turn','defense':'challenge','runs':0,'scores':[0,0]},
        {'inning':1,'bottom':1,'before':{'outs':0,'bases':1},'after':{'outs':0,'bases':2},'offense':'steal_attempt','defense':'intentional_walk','runs':0,'scores':[0,0]},
        {'inning':1,'bottom':1,'before':{'outs':0,'bases':2},'after':{'outs':1,'bases':0},'offense':'early_swing','defense':'challenge','runs':1,'scores':[0,1]}]
    history=[{'games':0,'validation':{'win_rate':.2},'choices':{},'probes':[{'role':'공격','inning':9,'difference':-2,'probabilities':{'early_swing':.2}},{'role':'수비','inning':9,'difference':-2,'probabilities':{'challenge':.5}}]},
        {'games':20,'validation':{'win_rate':.4},'choices':{},'probes':[{'role':'공격','inning':9,'difference':-2,'probabilities':{'early_swing':.6}},{'role':'수비','inning':9,'difference':-2,'probabilities':{'challenge':.9}}]}]
    return {'schema':'Match-whole-game-v1','status':'COMPLETED','supported_actions':['ordinary_turn','early_swing','steal_attempt','challenge','intentional_walk'],
        'action_names':{'ordinary_turn':'일반 타격 MOCK_TEST_ONLY','early_swing':'초구 공략','steal_attempt':'도루','challenge':'승부','intentional_walk':'고의볼넷'},
        'seeds':[{'seed':41,'history':history,'test_before':{'games':20,'wins':4,'win_rate':.2,'wilson_95':[.1,.4]},'test_after':{'games':20,'wins':8,'win_rate':.4,'wilson_95':[.2,.6]},
        'replay':{'learner_home':home,'innings':1,'home':1,'away':0,'events':events}}]}


def test_team_mapping_roles_and_no_synthetic_hit_or_pitch_stats():
    data=result();before=deepcopy(data);view=explain(data);run=view['runs'][0]
    assert view['evaluation']['test_after']=={'games':20,'wins':8}
    assert 'A팀 8승' in view['headline'] and 'B팀 12승' in view['headline']
    assert run['teams']['A']['runs']==1 and run['teams']['B']['allowed_runs']==1
    assert run['teams']['A']['steal_attempts']==1 and run['teams']['B']['pitch_choices']==[{'key':'challenge','label':'승부','count':1}]
    assert '고정' in run['teams']['B']['kind']
    assert [r['role'] for r in run['changes']]==['공격','수비']
    assert run['changes'][0]['difference']==-2 and run['changes'][1]['difference']==2
    assert not {'hits','strikeouts','pitch_type','velocity'}&run['teams']['A'].keys()
    assert data==before


def test_away_mapping_and_scene_team_assignments():
    view=explain(result(home=False));run=view['runs'][0]
    assert run['teams']['A']['venue']=='원정' and run['teams']['A']['runs']==0
    assert run['teams']['B']['runs']==1 and run['winner']=='B'
    assert run['scenes'][0]['attack']=='A' and run['scenes'][1]['attack']=='B'
    assert run['scenes'][1]['defense_choice']=='투구 전 도루 장면'


def test_running_report_has_no_fake_zero_win_rate_or_score():
    data=result();s=data['seeds'][0];s.pop('test_after');s.pop('test_before');s.pop('replay');data['status']='RUNNING'
    view=explain(data)
    assert view['evaluation']['test_after']['games']==0 and '기다리고' in view['headline']
    assert not view['runs'][0]['ready'] and view['runs'][0]['winner'] is None
    assert '평가가 끝나면' in view['growth']


def test_report_embeds_data_safely_and_does_not_mutate_saved_result():
    data=result();data['action_names']['early_swing']='</script><img src=x onerror=alert(1)>'
    before=deepcopy(data);page=render(data)
    assert '</script><img' not in page and '\\u003c/script' in page
    assert '한눈에 보기' in page and '경기 따라보기' in page and data==before
