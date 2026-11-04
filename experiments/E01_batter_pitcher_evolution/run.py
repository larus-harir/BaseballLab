"""E01 entry point; all rules, evaluation and tracking live in the parent package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from baseball_lab.cli import main

if __name__ == "__main__":
    main()
