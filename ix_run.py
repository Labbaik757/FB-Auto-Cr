"""
ixBrowser mode entry point — SEPARATE from main.py.

Usage:
    python ix_run.py

This file is intentionally standalone so main.py stays untouched.
It collects password + numbers (same prompts as main.py) and then
runs the ixBrowser automation (one account at a time, each with a
fresh randomized fingerprint).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.logo import logo
from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, EKL, LINE
from core.password_manager import select_password_config


def _render_config(config_state):
    """Simple config display (local version, main.py untouched)."""
    print(f"{LINE}")
    for k, v in config_state.items():
        print(f" {GREEN}[{RED}●{GREEN}] {WHITE}{k}: {CYAN}{v}")
    print(f"{LINE}")
from core.number_manager import process_file_input
from core.counter import Counter
from automation.ixbrowser_register import run_ixbrowser_mode


def main():
    logo()
    config_state = {"mode": "ixBrowser (fresh fingerprint)"}

    print(f"{CYAN}ixBrowser mode — each account gets a fresh randomized fingerprint.{WHITE}")
    print(f"{YELLOW}Requires: ixBrowser desktop client running with Local API enabled.{WHITE}")
    print(f"{LINE}")

    password_config = select_password_config(config_state, lambda: _render_config(config_state))
    _render_config(config_state)

    numbers = process_file_input()
    if numbers is None:
        input(f"\n {RED}Press Enter to exit...")
        return
    if not numbers:
        input(f"\n {RED}No numbers found. Press Enter to exit...")
        return

    _render_config(config_state)
    input(f"\n {WHITE}Press Enter to start ixBrowser automation... ")

    logo()
    counter = Counter()
    try:
        run_ixbrowser_mode(numbers, password_config, counter)
    except KeyboardInterrupt:
        print(f"\n\n {RED}Stopped by user.")
    except RuntimeError as e:
        print(f"\n {RED}{e}{WHITE}")

    input(f"\n {WHITE}Press Enter to exit... ")


if __name__ == "__main__":
    main()
