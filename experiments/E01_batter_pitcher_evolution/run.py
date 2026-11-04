import argparse
import json
from pathlib import Path
from baseball_lab.core.contracts import LeagueProfile, RuleSet
from baseball_lab.core.engine import Engine
from baseball_lab.outcome.synthetic import SyntheticOutcome
from baseball_lab.evaluation.matches import MatchSpec, evaluate
from baseball_lab.tracking.results import save

def main():
    parser = argparse.ArgumentParser(description="E01 synthetic baseline plate appearances; no training")
    parser.add_argument("--config", type=Path, default=Path(__file__).parent/"configs/m1_baseline.json")
    parser.add_argument("--output", type=Path, default=Path("outputs/E01"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    profile, rules = LeagueProfile(**config["profile"]), RuleSet(**config["rules"])
    engine = Engine(rules, profile, SyntheticOutcome())
    matches = [evaluate(engine, MatchSpec(b, p, config["seed"], config["plate_appearances"]))
               for b in config["batters"] for p in config["pitchers"]]
    save(args.output, profile, rules, matches, config)
    print("E01 M1 | synthetic probabilities | no training | no game wins measured")
    for m in matches:
        print(f"{m['match']['batter']:10} vs {m['match']['pitcher']:12}: PA={m['match']['plate_appearances']} {m['results']}")
    print(f"Saved {args.output / 'results.json'} and matchups.csv")

if __name__ == "__main__":
    main()
