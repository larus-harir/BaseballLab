"""Descriptive research measures, never rewards or claims of game victory."""

import math


def wilson_interval(successes: int, trials: int) -> list[float]:
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError("Invalid binomial counts")
    z = 1.959963984540054
    rate = successes / trials
    denom = 1 + z*z / trials
    center = (rate + z*z / (2*trials)) / denom
    radius = z * math.sqrt(rate*(1-rate)/trials + z*z/(4*trials*trials)) / denom
    return [max(0.0, center-radius), min(1.0, center+radius)]


def rates(counts: dict, keys: tuple, total: int) -> dict:
    return {key: counts.get(key, 0) / total for key in keys}
