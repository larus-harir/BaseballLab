"""MOCK_TEST_ONLY: unified routing retains stored source identities."""
from pathlib import Path
from test_web import web,call
from baseball_lab.matchup.web import render


def test_two_experiences_and_legacy_mlb_entry(web):
    wb,server=web
    _,body=call(server,'/');text=body.decode()
    assert 'href="/baseball"' not in text
    assert 'href="/eramatch"' in text and 'href="/match"' in text
    for path,project in [('/baseball','baseball'),('/eramatch?league=MLB','baseball'),('/eramatch?league=KBO','eramatch')]:
        code,body=call(server,path)
        assert code==200
        assert f"let project='{project}'" in body.decode()
        assert wb.token in body.decode()
        assert all(f'id="tab-{tab}"' in body.decode() for tab in ('duel','principles','developer'))


def test_inline_explanation_uses_saved_intermediates_and_separate_stages():
    html=render('eramatch')
    assert '__PRINCIPLES_SCRIPT__' not in html
    assert all(f'id="calc-{i:02}"' in html for i in range(1,8))
    assert 'batter_era' in html and 'batter_adjusted' in html
    assert 'r.simulation.sampling_bands' in html
    assert 'v.comparison[k].test.log_loss' in html
    assert '원본 가정' in html
    assert 'id="explanation"' not in html
    assert 'window.history.replaceState' in html
    assert 'function history(' not in html
