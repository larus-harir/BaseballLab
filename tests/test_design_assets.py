"""Offline report styling and one shared stylesheet per current screen."""
from test_strategy_view import mock_result
from baseball_lab.matchup.web import render as matchup,render_common
from baseball_lab.experiments.match.pitch_game.research import render as research
from baseball_lab.experiments.match.pitch_game.glance import render as glance
from baseball_lab.web.styles import apply_app_styles


def test_current_views_inline_shared_design_once_including_saved_reports():
    d=mock_result();d['schema']='Match-pitch-decision-game-v8'
    for html in (matchup('baseball'),render_common(),research(d),glance(d)):
        assert '__APP_STYLES__' not in html
        assert html.count('BaseballLab — shared field notes')==1
        assert 'Saved research reports share' in html
        assert '<link rel="stylesheet"' not in html


def test_legacy_html_without_design_token_is_unchanged(monkeypatch):
    import baseball_lab.web.styles as module
    def forbidden():raise AssertionError('Legacy render must not require new assets')
    monkeypatch.setattr(module,'app_styles',forbidden)
    html='<html>MOCK_TEST_ONLY archived report</html>'
    assert apply_app_styles(html)==html
