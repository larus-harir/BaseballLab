"""Manager-only fielding and running rules, using the existing KBO movements."""
from bisect import bisect_left, bisect_right
from collections import Counter
from functools import lru_cache
from random import Random

from . import season


@lru_cache(maxsize=16)
def fielding_ratings(seed):
    rng = Random(f'{seed}:fielding')
    return {key: rng.random() for key, profile in sorted(season.league()[0].items())
            if profile['role'] == 'batter'}


@lru_cache(maxsize=1)
def running_ratings():
    profiles, _, _, pools, _ = season.league()
    rates = {key: p['steal_attempt_rate'] for key, p in profiles.items()
             if p['role'] == 'batter' and p['steal_attempt_rate'] is not None}
    samples = sorted(rates[key] for key in pools['batter'] if key in rates)
    return {key: (bisect_left(samples, rate) + bisect_right(samples, rate)) / (2 * len(samples))
            for key, rate in rates.items()}


def field_contact(event, rating, single_to_out, rng):
    # Shift probability only between singles and the game's contact-out bucket.
    # Scale the reverse conversion by the matchup's single/out odds.
    effect = .12 * (2 * rating - 1)
    if event == 'single' and effect > 0 and rng.random() < effect:
        return 'other', 1
    if event == 'other' and effect < 0 and rng.random() < min(1., -effect * single_to_out):
        return 'single', -1
    return event, 0


@lru_cache(maxsize=3)
def first_to_third(outs):
    counts = season.movement_world().current.moves['fit'].get((outs, 1, 'single', False), {})
    hold, take = counts.get((0, 3, 0), 0), counts.get((0, 5, 0), 0)
    return tuple(counts), tuple(counts.values()), hold, take


def advance(world, outs, bases, event, runner_speed, rng):
    if bases == 1 and event == 'single' and runner_speed is not None:
        transitions, counts, hold, take = first_to_third(outs)
        if hold and take:
            odds = take * (1 + .5 * (2 * runner_speed - 1))
            faster = (hold + take) * odds / (hold + odds)
            weights = [hold + take - faster if t == (0, 3, 0) else faster if t == (0, 5, 0) else n
                       for t, n in zip(transitions, counts)]
            delta, end, runs = rng.choices(transitions, weights=weights, k=1)[0]
            return outs + delta, end, runs
    return world.advance(outs, bases, event, rng)


@lru_cache(maxsize=1)
def run_expectancy():
    """Mean runs left in each base/out state from KBO fit-set transitions."""
    import numpy as np

    movements = season.movement_world().current.moves['fit']
    rows = [Counter() for _ in range(24)]
    for (outs, bases, _, bunt), counts in movements.items():
        if not bunt:
            rows[outs * 8 + bases].update(counts)
    equations = np.eye(24)
    runs = np.zeros(24)
    for i, counts in enumerate(rows):
        total = sum(counts.values())
        for (delta, end, scored), amount in counts.items():
            probability = amount / total
            runs[i] += probability * scored
            next_outs = i // 8 + delta
            if next_outs < 3:
                equations[i, next_outs * 8 + end] -= probability
    return (*map(float, np.linalg.solve(equations, runs)), 0.)
