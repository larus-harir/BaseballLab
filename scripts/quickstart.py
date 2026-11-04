"""Run from any directory, with or without an editable package installation."""
import runpy
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
runpy.run_path(str(root / "experiments/E01_batter_pitcher_evolution/run.py"), run_name="__main__")
