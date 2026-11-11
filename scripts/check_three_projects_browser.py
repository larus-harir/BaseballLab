"""Compatibility entry point for the current three-project acceptance checks.

The earlier screenshots remain historical evidence. The current checks exercise
same routes plus automatic data preparation, 2023, keyboard and mobile replay.
Requires Playwright/Chromium and the privately stored registered source data.
"""
from check_incremental_browser import main


if __name__=='__main__':main()
