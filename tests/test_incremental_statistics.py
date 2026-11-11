"""MOCK_TEST_ONLY records exercise scientific boundaries, not fake research data."""
import math

import pytest

from baseball_lab.data.knowledge import get_knowledge
from baseball_lab.evaluation.sabermetrics import batting_metrics
from baseball_lab.matchup.models import EVENTS
from baseball_lab.matchup.validation import (
    METHODS, evaluate_same_test, paired_game_bootstrap, split_by_completed_game,
    validate_external, validate_rows,
)


def mock_rows():
    rows = []
    for stage, date in [('fit', '20230401'), ('validation', '20230720'), ('test', '20230901')]:
        for game_number in range(2):
            for i, event in enumerate(EVENTS):
                rows.append({'id': f'MOCK_TEST_ONLY:{stage}:{game_number}:{i}',
                             'game': f'MOCK_TEST_ONLY:{stage}:{game_number}', 'date': date,
                             'batter': 'MOCK_TEST_ONLY_b', 'pitcher': 'MOCK_TEST_ONLY_p', 'event': event})
    return rows


def test_suspended_game_uses_last_actual_availability_and_no_duplicates():
    rows = mock_rows() + [
        {'id': 'MOCK_TEST_ONLY:suspended:1', 'game': 'BOS202306260', 'date': '20230626',
         'batter': 'MOCK_TEST_ONLY_b', 'pitcher': 'MOCK_TEST_ONLY_p', 'event': 'walk'},
        {'id': 'MOCK_TEST_ONLY:suspended:2', 'game': 'BOS202306260', 'date': '20230826',
         'batter': 'MOCK_TEST_ONLY_b', 'pitcher': 'MOCK_TEST_ONLY_p', 'event': 'walk'},
    ]
    parts, meta = split_by_completed_game(rows, 2023)
    assert len(parts['fit']) == 16 and len(parts['test']) == 18
    assert meta['test']['available_dates'][0] == '20230826'
    assert not {r['game'] for r in parts['fit']} & {r['game'] for r in parts['test']}
    with pytest.raises(ValueError, match='중복'):
        split_by_completed_game(rows + [rows[0]], 2023)
    with pytest.raises(ValueError, match='시즌'):
        split_by_completed_game([{**r, 'date': '20250401'} for r in rows], 2023)


def test_uniform_cold_start_baseline_has_known_proper_scoring_values():
    rows = mock_rows()[-16:]
    league = {event: 1 / 8 for event in EVENTS}
    study, games = evaluate_same_test(rows, {}, {}, league, strength=300)
    assert study['coverage']['both_players_seen_n'] == 0
    assert study['coverage']['cold_start_n'] == 16
    for method in METHODS:
        values = study['models'][method]
        assert values['n'] == 16
        assert values['log_loss'] == pytest.approx(math.log(8))
        assert values['brier'] == pytest.approx(7 / 8)
        assert values['zero_observation_probability_n'] == 0
        assert sum(bin['n'] for bin in values['hit_calibration']) == 16
    result = paired_game_bootstrap(games, repetitions=40)
    assert result == paired_game_bootstrap(games, repetitions=40)
    for method in result['comparison'].values():
        assert method['log_loss']['difference_vs_league'] == pytest.approx(0)
        assert method['log_loss']['paired_game_percentile_95'] == pytest.approx([0, 0])
    assert result['log5_vs_binary_normalized_candidate']['log_loss']['paired_game_percentile_95'] == pytest.approx([0, 0])


def test_fixed_strength_evaluation_keeps_validation_unused_and_counts_all_subgroups():
    rows = mock_rows()
    rows[-1] = {**rows[-1], 'batter': 'MOCK_TEST_ONLY_unseen'}
    result = validate_rows(rows, year=2023, strength=300, bootstrap_repetitions=40)
    assert result['strength'] == 300 and result['target_season_tuning'] is False
    assert result['validation_used_for_selection'] is False
    assert result['test']['n'] == 16 and result['test']['coverage']['cold_start_n'] == 1
    for method in METHODS:
        cold = result['test']['subgroups']['cold_start'][method]['n']
        seen = result['test']['subgroups']['both_seen'][method]['n']
        assert cold + seen == result['test']['models'][method]['n']
    assert 'refitting' in result['uncertainty']['scope']


def test_missing_fit_event_is_rejected_without_pseudocount_invention():
    rows = mock_rows()[-16:]
    league = {event: 1 / 7 if event != 'triple' else 0. for event in EVENTS}
    with pytest.raises(ValueError, match='임의 확률'):
        evaluate_same_test(rows, {}, {}, league, strength=300)
    with pytest.raises(ValueError):
        evaluate_same_test(rows, {}, {}, {event: 1 / 8 for event in EVENTS}, strength=float('nan'))
    with pytest.raises(ValueError):
        paired_game_bootstrap({}, repetitions=1)
    assert paired_game_bootstrap({}, repetitions=40)['available'] is False


def test_external_validation_rejects_identical_seasons_before_reading_sources(tmp_path):
    from unittest.mock import patch
    with patch('baseball_lab.data.catalog.DatasetCatalog') as catalog:
        with pytest.raises(ValueError, match='독립 시즌'):
            validate_external(tmp_path, year=2024, reference_year=2024)
        catalog.assert_not_called()


def test_metric_denominators_and_knowledge_do_not_assert_all_inputs_are_used():
    counts = {'PA': 100, 'AB': 80, 'H': 30, '2B': 4, '3B': 1, 'HR': 5,
              'SO': 10, 'BB': 10, 'HBP': 2, 'SF': 5, 'SH': 3}
    metrics = batting_metrics(counts)
    assert metrics['AVG'].value == pytest.approx(30 / 80)
    assert metrics['OBP'].value == pytest.approx(42 / 97)
    assert metrics['SLG'].value == pytest.approx(51 / 80)
    assert metrics['AVG'].denominator != counts['PA'] - counts['BB']
    registry = get_knowledge()
    assert {m['id'] for m in registry['metrics']} == {
        'AVG', 'OBP', 'SLG', 'OPS', 'BABIP', 'K%', 'BB%', 'K/9', 'BB/9',
        'FIP', 'wOBA', 'wRC+', 'WAR', 'DIPS', 'Log5',
    }
    assert get_knowledge('Log5')['used_in_active_probability_model'] is True
    assert get_knowledge('WAR')['used_in_active_probability_model'] is False
    assert 'IP_OUTS' in get_knowledge('K/9')['required_fields']
    assert 'cFIP' in get_knowledge('FIP')['required_fields']
    assert get_knowledge('WAR')['numerator'] is None
    get_knowledge('BABIP')['cautions'].clear()
    assert get_knowledge('BABIP')['cautions']
    with pytest.raises(ValueError):
        get_knowledge('MOCK_TEST_ONLY_unregistered_metric')


def test_independent_check_does_not_download_missing_original(tmp_path):
    from unittest.mock import patch
    with patch('baseball_lab.data.catalog.DatasetCatalog') as registry, patch('baseball_lab.r1.provider.acquire') as acquire:
        registry.return_value.get.side_effect=[{}, {'models':{'normalized':{'strength':300}}}, None]
        with pytest.raises(ValueError,match='다운로드하지 않습니다'):
            validate_external(tmp_path)
        registry.return_value.get.assert_called_with('match',season=2023)
        acquire.assert_not_called()
