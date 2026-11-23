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


def test_total_progress_crosses_run_boundaries_without_resetting():
    rows=[parse(PREFIX+'{"completed":'+str(n)+',"total":153,"phase":"training"}') for n in (0,51,51,102,102,153)]
    assert [r['completed_episodes'] for r in rows]==[0,51,51,102,102,153]
    assert all(r['target_episodes']==153 and r['progress_scope']=='all_runs' for r in rows)
    for bad in ('null','[]','{}','{"completed":true,"total":153,"phase":"training"}','{"completed":154,"total":153,"phase":"training"}','{"completed":0,"total":153,"phase":"other"}'):
        assert parse(PREFIX+bad) is None
    assert parse('학습 10/51경기') is None
