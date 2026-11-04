"""Paired-side, fixed-seed game evaluation; training never runs here."""
from random import Random

from baseball_lab.agents.game_baselines import GameBaseline
from baseball_lab.core.game import Team


def paired_win_interval(pair_wins, seed):
    """Percentile bootstrap that resamples whole home/away pairs, not single games."""
    if len(pair_wins) < 2:
        return [0., 1.]
    rng = Random(f"pair-bootstrap:{seed}")
    draws = sorted(sum(rng.choice(pair_wins) for _ in pair_wins)/(2*len(pair_wins)) for _ in range(1000))
    return [draws[24], draws[974]]


def baseline_teams():
    return [Team('random_team', GameBaseline('batter'), GameBaseline('pitcher')),
            Team('attack_team', GameBaseline('batter', 'aggressive'), GameBaseline('pitcher', 'mixed')),
            Team('patient_team', GameBaseline('batter', 'patient'), GameBaseline('pitcher', 'strike_first'))]


def evaluate_team(engine, candidate, opponents, seed=100000, pairs=10):
    if type(pairs) is not int or pairs < 1:
        raise ValueError('pairs must be positive')
    results = []
    for opponent in opponents:
        wins = losses = draws = runs_for = runs_against = 0
        pair_wins = []
        for pair in range(pairs):
            pair_win = 0
            game_seed = seed + pair
            for side in (0, 1):
                game = engine.play(candidate, opponent, game_seed) if side == 0 else engine.play(opponent, candidate, game_seed)
                reward = game.reward(side)
                pair_win += reward == 1
                wins += reward == 1
                losses += reward == -1
                draws += reward == 0
                scores = (game.away_score, game.home_score)
                runs_for += scores[side]; runs_against += scores[1-side]
            pair_wins.append(pair_win)
        games = pairs*2
        results.append({'opponent': opponent.name, 'games': games, 'wins': wins, 'losses': losses, 'draws': draws,
                        'win_rate': wins/games, 'score_rate': (wins+.5*draws)/games,
                        'win_ci95': paired_win_interval(pair_wins, seed), 'interval_method': 'paired-bootstrap-1000', 'pair_wins': pair_wins, 'runs_for': runs_for/games, 'runs_against': runs_against/games})
    return results
