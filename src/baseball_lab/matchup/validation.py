"""Read-only, retrospective independent-season checks of the shared PA models.

Nothing here tunes a setting on the target season or writes a player catalog.
The binary candidate is deliberately named as an exploratory construction: it
combines separate one-versus-rest Log5 estimates, then normalizes them. It is
neither the KBO assignment's ordered sampler nor a theoretically preferred model.
"""
from collections import defaultdict
import math
from pathlib import Path
from random import Random

from baseball_lab.data.lineage import checksum, content_hash, utc_now
from baseball_lab.evaluation.sabermetrics import validate_probability_distribution
from .mlb import observed_rows, tally
from .models import EVENTS, MODEL_VERSION, distribution, generalized_log5, log5, stabilize

METHODS = ('league', 'batter', 'log5', 'binary_normalized_candidate')
HITS = ('single', 'double', 'triple', 'home_run')


def split_by_completed_game(rows, year):
    """Availability is last actual PA date, not the possibly suspended game ID."""
    if type(year) is not int or year not in (2023, 2024):
        raise ValueError('독립 검사 대상으로 확인한 2023·2024 시즌만 지원합니다.')
    if not rows or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('중복 없는 실제 타석이 필요합니다.')
    completed = {}
    for row in rows:
        if not all(row.get(k) for k in ('id', 'game', 'batter', 'pitcher', 'date')):
            raise ValueError('타석·선수 식별자와 실제 날짜가 필요합니다.')
        if not row['date'].startswith(str(year)) or row['event'] not in EVENTS:
            raise ValueError('선택한 시즌과 타석 사건 정의를 확인하세요.')
        completed[row['game']] = max(completed.get(row['game'], ''), row['date'])
    before, after = f'{year}0715', f'{year}0825'
    parts = {'fit': [], 'validation': [], 'test': []}
    for row in rows:
        date = completed[row['game']]
        stage = 'fit' if date < before else 'validation' if date < after else 'test'
        parts[stage].append(row)
    if any(not values for values in parts.values()):
        raise ValueError('서로 다른 경기로 구성된 세 기간이 필요합니다.')
    games = {stage: {r['game'] for r in values} for stage, values in parts.items()}
    if any(games[a] & games[b] for a, b in (('fit', 'validation'), ('fit', 'test'), ('validation', 'test'))):
        raise ValueError('기간 사이에 같은 경기가 섞여 있습니다.')
    metadata = {
        stage: {'n': len(values), 'games': len(games[stage]),
                'record_hash': content_hash([r['id'] for r in values]),
                'available_dates': [min(completed[r['game']] for r in values),
                                    max(completed[r['game']] for r in values)]}
        for stage, values in parts.items()
    }
    return parts, metadata


def _empty_metrics():
    return {'n': 0, 'log_loss_sum': 0., 'brier_sum': 0., 'zero_observation_probability_n': 0}


def _finish_metrics(stats):
    n = stats['n']
    return {'n': n,
            'log_loss': stats['log_loss_sum'] / n if n and not stats['zero_observation_probability_n'] else None,
            'brier': stats['brier_sum'] / n if n else None,
            'zero_observation_probability_n': stats['zero_observation_probability_n']}


def _probabilities(batter, pitcher, league):
    binary = {event: log5(batter[event], pitcher[event], league[event]) for event in EVENTS}
    binary_total = sum(binary.values())
    models = {'league': dict(league), 'batter': batter,
              'log5': generalized_log5(batter, pitcher, league)[0],
              'binary_normalized_candidate': {event: binary[event] / binary_total for event in EVENTS}}
    for values in models.values():
        validate_probability_distribution(values)
    return models


def evaluate_same_test(rows, batters, pitchers, league, *, strength):
    """All candidates score the identical observed records and fit-only priors."""
    if type(strength) not in (int, float) or not math.isfinite(strength) or strength <= 0:
        raise ValueError('고정 보정 강도는 유한한 양수여야 합니다.')
    validate_probability_distribution(league)
    if set(league) != set(EVENTS) or any(not 0 < value < 1 for value in league.values()):
        raise ValueError('기준 기간에 모든 배타적 사건의 관측이 필요합니다. 임의 확률로 채우지 않습니다.')
    if not rows:
        raise ValueError('평가할 타석이 없습니다.')
    summaries = {method: _empty_metrics() for method in METHODS}
    subgroups = {name: {method: _empty_metrics() for method in METHODS}
                 for name in ('both_seen', 'cold_start', 'small_fit_sample', 'larger_fit_sample')}
    calibration = {method: [{'n': 0, 'predicted_sum': 0., 'observed_sum': 0} for _ in range(10)]
                   for method in METHODS}
    event_stats = {method: {event: {'n': 0, 'predicted_sum': 0., 'observed_sum': 0}
                           for event in EVENTS} for method in METHODS}
    game_scores = defaultdict(lambda: {'n': 0, **{method: {'log_loss_sum': 0., 'brier_sum': 0.}
                                                    for method in METHODS}})
    pairs = {}; cold_n = small_n = 0
    for row in rows:
        identity = row['batter'], row['pitcher']
        if identity not in pairs:
            b_counts = batters.get(identity[0], {event: 0 for event in EVENTS})
            p_counts = pitchers.get(identity[1], {event: 0 for event in EVENTS})
            cold = identity[0] not in batters or identity[1] not in pitchers
            small = min(sum(b_counts.values()), sum(p_counts.values())) < 100
            predictions = _probabilities(stabilize(b_counts, league, strength),
                                         stabilize(p_counts, league, strength), league)
            pairs[identity] = predictions, cold, small
        predictions, cold, small = pairs[identity]
        cold_n += cold; small_n += small
        groups = ('cold_start' if cold else 'both_seen', 'small_fit_sample' if small else 'larger_fit_sample')
        game = game_scores[row['game']]; game['n'] += 1
        event = row['event']
        for method, q in predictions.items():
            prob = q[event]; loss = -math.log(prob) if prob > 0 else None
            brier = sum((q[e] - (e == event)) ** 2 for e in EVENTS)
            for stats in (summaries[method], *(subgroups[group][method] for group in groups)):
                stats['n'] += 1; stats['brier_sum'] += brier
                if loss is None:stats['zero_observation_probability_n'] += 1
                else:stats['log_loss_sum'] += loss
            if loss is not None:game[method]['log_loss_sum'] += loss
            game[method]['brier_sum'] += brier
            hit = sum(q[e] for e in HITS)
            bucket = calibration[method][min(9, int(hit * 10))]
            bucket['n'] += 1; bucket['predicted_sum'] += hit; bucket['observed_sum'] += event in HITS
            for e in EVENTS:
                event_stats[method][e]['n'] += 1
                event_stats[method][e]['predicted_sum'] += q[e]
                event_stats[method][e]['observed_sum'] += event == e
    result = {
        'n': len(rows), 'games': len(game_scores),
        'record_hash': content_hash([r['id'] for r in rows]),
        'models': {method: {**_finish_metrics(stats), 'hit_calibration': calibration[method],
                            'event_calibration': event_stats[method]}
                   for method, stats in summaries.items()},
        'coverage': {'predicted_n': len(rows), 'prediction_fraction': 1.,
                     'both_players_seen_n': len(rows) - cold_n,
                     'both_players_seen_fraction': (len(rows) - cold_n) / len(rows),
                     'cold_start_n': cold_n, 'small_fit_sample_n': small_n,
                     'cold_start_rule': 'Unknown side uses the fit-period league distribution, not future player records.',
                     'small_sample_rule': 'At least one fit-period player denominator below 100 PA/TBF; threshold is a reporting group, not a filter.'},
        'subgroups': {name: {method: _finish_metrics(stats) for method, stats in methods.items()}
                     for name, methods in subgroups.items()},
    }
    return result, dict(game_scores)


def paired_game_bootstrap(game_scores, *, repetitions=200, seed=20261111):
    """Resample whole games and compare logloss/Brier against the same league baseline."""
    if type(repetitions) is not int or not 20 <= repetitions <= 1000 or type(seed) is not int:
        raise ValueError('경기 단위 반복 검사는 20~1,000회와 정수 재현 번호가 필요합니다.')
    games = [game_scores[key] for key in sorted(game_scores)]
    if len(games) < 2:
        return {'available': False, 'reason': '경기가 두 개 이상 있어야 경기 단위 변동을 검사할 수 있습니다.'}
    rng = Random(seed); samples = {method: {'log_loss': [], 'brier': []} for method in METHODS if method != 'league'}
    for _ in range(repetitions):
        chosen = [games[rng.randrange(len(games))] for _ in games]
        n = sum(game['n'] for game in chosen)
        for method, metrics in samples.items():
            for metric in metrics:
                field = metric + '_sum'
                metrics[metric].append(sum(game[method][field] - game['league'][field] for game in chosen) / n)
    total_n = sum(game['n'] for game in games)
    comparison = {}
    for method, metrics in samples.items():
        comparison[method] = {}
        for metric, values in metrics.items():
            ordered = sorted(values); field = metric + '_sum'
            comparison[method][metric] = {
                'difference_vs_league': sum(game[method][field] - game['league'][field] for game in games) / total_n,
                'paired_game_percentile_95': [ordered[int((repetitions - 1) * .025)], ordered[int((repetitions - 1) * .975)]],
            }
    direct = {}
    for metric in ('log_loss', 'brier'):
        differences = sorted(a - b for a, b in zip(samples['log5'][metric], samples['binary_normalized_candidate'][metric]))
        field = metric + '_sum'
        direct[metric] = {
            'difference': sum(game['log5'][field] - game['binary_normalized_candidate'][field] for game in games) / total_n,
            'paired_game_percentile_95': [differences[int((repetitions - 1) * .025)], differences[int((repetitions - 1) * .975)]],
        }
    return {'available': True, 'games': len(games), 'repetitions': repetitions, 'seed': seed,
            'method': 'Paired percentile bootstrap of whole games; ratio of resampled summed loss to resampled PA count.',
            'comparison': comparison, 'log5_vs_binary_normalized_candidate': direct,
            'scope': 'Sampling variation across observed test games only; no refitting, model-selection, missing-data or causal uncertainty. Games share players and calendar patterns not fully captured by game resampling. Negative differences favor the candidate on these observed games.'}


def validate_rows(rows, *, year, strength, bootstrap_repetitions=200):
    """Pure computation entry point; synthetic inputs are only used in tests."""
    parts, split = split_by_completed_game(rows, year)
    batters, pitchers = tally(parts['fit'], 'batter'), tally(parts['fit'], 'pitcher')
    league = distribution({e: sum(counts[e] for counts in batters.values()) for e in EVENTS})
    evaluation, games = evaluate_same_test(parts['test'], batters, pitchers, league, strength=strength)
    uncertainty = paired_game_bootstrap(games, repetitions=bootstrap_repetitions)
    return {'split': split, 'strength': strength, 'target_season_tuning': False,
            'validation_used_for_selection': False, 'test': evaluation, 'uncertainty': uncertainty}


def validate_external(root, year=2023, reference_year=2024, *, bootstrap_repetitions=200):
    """Read registered existing data only; preparation is the catalog's separate responsibility."""
    if year == reference_year:
        raise ValueError('독립 시즌 검사는 대상 시즌과 설정을 선택한 기준 시즌이 달라야 합니다.')
    from baseball_lab.data.catalog import DatasetCatalog
    root = Path(root); catalog = DatasetCatalog(root)
    data = catalog.get('baseball', season=year); reference = catalog.get('baseball', season=reference_year)
    if data is None or reference is None:
        raise ValueError('대상 시즌과 기준 시즌의 검증된 로컬 선수 자료를 먼저 준비하세요.')
    strength = reference['models']['normalized']['strength']
    original = catalog.get('match', season=year)
    if original is None:
        raise ValueError('해당 시즌의 공식 원본을 공통 자료 준비에서 먼저 연결하세요. 검증 조회에서는 다운로드하지 않습니다.')
    rows = observed_rows(original['manifest']['parsed_csv_path'])
    result = validate_rows(rows, year=year, strength=strength, bootstrap_repetitions=bootstrap_repetitions)
    result.update({'schema': 'retrospective-independent-season-validation-v1', 'created_at': utc_now(),
                   'target_year': year, 'reference_year': reference_year,
                   'dataset_ids': [data['dataset_id'], reference['dataset_id']],
                   'source': {k: data['source'][k] for k in ('id', 'source_url', 'files', 'license')},
                   'parameter_selection': {'source_dataset_id': reference['dataset_id'],
                       'selected_strength': strength, 'rule': 'Reuse the reference season validation choice; target validation/test never selects a setting.'},
                   'model_versions': {'log5': MODEL_VERSION, 'binary_normalized_candidate': 'one-vs-rest-log5-normalized-study-v1'},
                   'code_sha256': {p.name: checksum(p) for p in (Path(__file__), Path(__file__).with_name('models.py'))},
                   'scope': 'Retrospective check of an independent season, with player profiles/prior fitted only on that season early period. 2024-selected settings applied to 2023 are not a prospective forecast.',
                   'limitations': ['Same-season early player observations are required; this does not transfer 2024 player ability into 2023.',
                                   '2023 was also used in prior Match work; this statistic-model check is independent of the 2024 tuning but not a preregistered untouched scientific dataset.',
                                   'Event prediction does not validate KBO, cross-era fairness, unobserved action effects, or nine-inning outcomes.',
                                   'The one-versus-rest normalized binary model is an exploratory comparison and is never automatically selected by this report.']})
    return result
