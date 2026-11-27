"""MOCK_TEST_ONLY narratives must follow evidence, including contradictions."""
from copy import deepcopy
import pytest
from baseball_lab.experiments.match.pitch_game.explanations import explain
from baseball_lab.web.training_progress import parse,PREFIX


def sample(signal=.2):
    return {'preferences':{v:({'before':{'family:cutter':.2},'after':{'family:cutter':.4}} if v=='defense' else {'before':{},'after':{}}) for v in ('offense','direction','defense','course')},
        'feedback':{'defense':{'family:cutter':{'decisions':100,'mean_advantage':signal,'hits':10,'events':{'out':50},'strikeouts':10}},'offense':{},'direction':{},'course':{}}}


def test_explanation_connects_cutter_and_observed_height_without_inventing_a_cause():
    d=sample();old=deepcopy(d)
    counts={'pitch:cutter:left_high:fast':30,'pitch:cutter:right_high:fast':40,'pitch:cutter:left_low:fast':20,'pitch:cutter:any:missing':10}
    details={k:{'decisions':n,'hits':n//10,'strikeouts':n//5} for k,n in counts.items()}
    r=explain(d,counts,details)[0]
    assert d==old and '커터를 더 자주' in r['summary'] and '상대적으로 좋은' in r['reason']
    assert r['pattern']['count']==70 and r['pattern']['known']==90 and r['pattern']['decisions']==70
    assert '높은 코스' in r['context'] and '이 구종·높이 조합' in r['observed']
    assert '땅볼' not in str(r) and '때문에' not in r['reason']
    d['preferences']['defense']['before']['family:cutter']=.5
    assert '최종 선호는 줄었습니다' in explain(d,counts,details)[0]['reason']


@pytest.mark.parametrize('signal',[None,0.,-.2])
def test_missing_neutral_or_negative_signals_never_become_a_success_story(signal):
    r=explain(sample(signal),{})[0]
    assert '상대적으로 좋은' not in r['reason'] and r['pattern'] is None
    if signal is None:assert '남아 있지 않아' in r['reason']
    elif signal<0:assert '불리' in r['reason'] and '함께' in r['reason']
    else:assert '뚜렷한 방향이 없' in r['reason']


@pytest.mark.parametrize('before',[.4,.5])
def test_family_ranking_is_scoped_even_when_intentional_walk_is_more_likely(before):
    d=sample();d['preferences']['defense']={'before':{'family:cutter':before,'intentional_walk':1-before},
                                         'after':{'family:cutter':.4,'intentional_walk':.6}}
    r=explain(d,{})[0]
    assert r['action']=='family:cutter' and '구종 중 가장 선호' in r['summary']
    assert r['summary'].startswith('같은 기준 상황에서 ')
    assert '가상 연습' in r['observed']


def test_intentional_walk_uses_decisions_instead_of_pitch_denominator():
    d=sample();d['preferences']['defense']={'before':{'pitch':.5,'intentional_walk':.5},
                                         'after':{'pitch':.3,'intentional_walk':.7}}
    d['feedback']['defense']={'intentional_walk':{'decisions':20,'mean_advantage':None,'events':{'walk':20},
                                                'terminal_results':{'walk':20}}}
    r=explain(d,{})[0]
    assert r['action']=='intentional_walk'
    assert '선택 100회당 볼넷 100.0회' in r['observed']
    assert '100구' not in r['observed'] and '가상 연습' in r['observed']


def test_unchanged_policy_and_missing_heights_do_not_create_unobserved_changes():
    d=sample(None);d['preferences']['defense']['before']={'family:cutter':.4}
    r=explain(d,{'pitch:cutter:left_high:fast':10,'pitch:cutter:any:missing':100})[0]
    assert r['delta']==0 and '달라졌' not in r['reason']
    assert '코스 높이가 기록된 선택' in r['context']
    assert r['pattern']['count']==r['pattern']['known']==10


def test_total_progress_crosses_run_boundaries_without_resetting():
    rows=[parse(PREFIX+'{"completed":'+str(n)+',"total":153,"phase":"training"}') for n in (0,51,51,102,102,153)]
    assert [r['completed_episodes'] for r in rows]==[0,51,51,102,102,153]
    assert all(r['target_episodes']==153 and r['progress_scope']=='all_runs' for r in rows)
    for bad in ('null','[]','{}','{"completed":true,"total":153,"phase":"training"}','{"completed":154,"total":153,"phase":"training"}','{"completed":0,"total":153,"phase":"other"}'):
        assert parse(PREFIX+bad) is None
    assert parse('학습 10/51경기') is None
