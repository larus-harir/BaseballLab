import pytest
from baseball_lab.evaluation.sabermetrics import batting_metrics,validate_probability_distribution


def test_official_denominators_and_ops_is_not_probability():
    m=batting_metrics({'PA':120,'AB':100,'H':40,'2B':10,'3B':1,'HR':8,'SO':20,'BB':10,'HBP':5,'SF':5,'SH':0})
    assert m['BABIP'].value==pytest.approx(32/77)
    assert m['OBP'].value==pytest.approx(55/120)
    assert m['SLG'].value==pytest.approx(76/100)
    assert m['OPS'].value>1
    assert m['K_RATE'].denominator==120


def test_missing_sacrifice_fly_or_hbp_is_not_zero():
    m=batting_metrics({'AB':100,'H':30,'HR':5,'SO':20,'BB':10})
    assert m['AVG'].value==.3
    assert m['BABIP'].value is None and 'SF' in m['BABIP'].reason
    assert m['OBP'].value is None and 'HBP' in m['OBP'].reason
    assert m['OPS'].value is None


def test_zero_denominator_and_impossible_counts():
    assert batting_metrics({'AB':0,'H':0})['AVG'].value is None
    with pytest.raises(ValueError):batting_metrics({'AB':10,'H':9,'SO':2})
    with pytest.raises(ValueError):batting_metrics({'AB':100,'H':10,'2B':8,'3B':4,'HR':0})
    with pytest.raises(ValueError):batting_metrics({'HP':3})


def test_independent_log5_events_cannot_silently_overflow():
    with pytest.raises(ValueError,match='합이 1'):
        validate_probability_distribution({'K':.5,'BB':.4,'HR':.3,'BIP':0.})
    validate_probability_distribution({'K':.2,'BB':.1,'HR':.05,'BIP':.65})
