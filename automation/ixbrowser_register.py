"""
ixBrowser-based Facebook account registration.

Flow per account (sequential, one by one):
  1. Create a FRESH ixBrowser profile (or reuse a pre-created pool).
  2. Open it with a RANDOMIZED fingerprint via ixBrowser Local API.
  3. Attach Playwright to the running profile with connect_over_cdp().
  4. Run the same human-like signup steps as browser_register.py.
  5. Save result, close the ixBrowser profile.

This file IMPORTS the signup helpers from automation.browser_register
— it does NOT duplicate or modify that file.

Requires:
    pip install ixbrowser-local-api playwright
    ixBrowser desktop client running with Local API enabled.
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, LINE
from ui.display import print_lock
from core.counter import Counter
from core.ixbrowser_client import get_ixbrowser, IXBROWSER_AVAILABLE

# Reuse the human-like signup implementation (no duplication, no edits).
from automation.browser_register import browser_create_account, _parse_number_entry


def _cdp_url(debugging_address):
    """Build a ws:// CDP endpoint from ixBrowser's debugging_address."""
    addr = debugging_address.strip()
    if addr.startswith("http"):
        # e.g. http://127.0.0.1:9222 -> ws://127.0.0.1:9222
        addr = addr.replace("http://", "ws://").replace("https://", "wss://")
    elif not addr.startswith("ws"):
        addr = "ws://" + addr
    return addr


def run_ixbrowser_mode(numbers, password_config, counter=None):
    """
    Run ixBrowser automation for a list of numbers (sequential).

    Args:
        numbers: List of phone numbers
        password_config: Dict with password settings (same as browser mode)
        counter: Optional Counter instance
    """
    if not PLAYWRIGHT_AVAILABLE:
        print(f"{RED}Playwright not installed. Run: pip install playwright{WHITE}")
        return
    if not IXBROWSER_AVAILABLE:
        print(f"{RED}ixbrowser-local-api not installed. Run: pip install ixbrowser-local-api{WHITE}")
        return

    from core.password_manager import generate_random_password
    from core.path_manager import get_output_dir

    def _get_password(cfg):
        if cfg and cfg.get("type") == "fixed" and cfg.get("value"):
            return cfg["value"]
        return generate_random_password()

    if counter is None:
        counter = Counter()

    # Connect to ixBrowser local API
    ixb, ix_cfg = get_ixbrowser()
    with print_lock:
        print(f"{CYAN}[ixBrowser] Connecting to API at {ixb.target}:{ixb.port}...{WHITE}")
    ixb.ping()
    with print_lock:
        print(f"{GREEN}[ixBrowser] API reachable.{WHITE}")

    delete_after = bool(ix_cfg.get("delete_profile_after", False))

    with sync_playwright() as p:
        for idx, entry in enumerate(numbers, 1):
            number, sms_url = _parse_number_entry(entry)
            profile_id = None
            try:
                with print_lock:
                    print(f"\n{LINE}")
                    print(f"{CYAN}[{idx}/{len(numbers)}] {number} — creating ixBrowser profile...{WHITE}")

                # 1. Fresh profile per account (random fingerprint at creation)
                profile_name = f"FB-Auto-Cr-{idx}-{random.randint(1000, 9999)}"
                profile_id = ixb.create_fresh_profile(profile_name)

                # 2. Open with randomized fingerprint -> get CDP address
                debugging_address, _webdriver = ixb.open_with_random_fingerprint(profile_id)
                with print_lock:
                    print(f"{CYAN}[ixBrowser] Profile {profile_id} opened ({debugging_address}){WHITE}")

                # 3. Attach Playwright to the running ixBrowser profile
                browser = p.chromium.connect_over_cdp(_cdp_url(debugging_address))
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()

                try:
                    password = _get_password(password_config)
                    result = browser_create_account(page, number, password, counter, sms_url)

                    if result["status"] == "success":
                        output_dir = get_output_dir()
                        os.makedirs(output_dir, exist_ok=True)
                        with open(os.path.join(output_dir, "ixbrowser_accounts.txt"), "a") as f:
                            f.write(result["result_line"] + "\n")
                finally:
                    # Detach Playwright (do NOT close the browser here;
                    # ixBrowser manages the profile lifecycle).
                    try:
                        browser.close()
                    except Exception:
                        pass

                # 4. Close (and optionally delete) the ixBrowser profile
                try:
                    ixb.close_profile(profile_id)
                except Exception as e:
                    with print_lock:
                        print(f"{YELLOW}[ixBrowser] close_profile warning: {e}{WHITE}")
                if delete_after:
                    try:
                        ixb.delete_profile(profile_id)
                    except Exception as e:
                        with print_lock:
                            print(f"{YELLOW}[ixBrowser] delete_profile warning: {e}{WHITE}")
                profile_id = None

            except Exception as e:
                with print_lock:
                    print(f"{RED}[ixBrowser] ERROR for {number}: {e}{WHITE}")
                if counter:
                    counter.increment("error")
                # Best-effort cleanup of a half-opened profile
                if profile_id:
                    try:
                        ixb.close_profile(profile_id)
                    except Exception:
                        pass
            finally:
                if idx < len(numbers):
                    pause = random.uniform(10, 20)
                    with print_lock:
                        print(f"{YELLOW}Waiting {pause:.0f}s before next account...{WHITE}")
                    time.sleep(pause)

        # Summary
        s = counter.summary()
        with print_lock:
            print(f"\n{LINE}")
            print(f" {GREEN}[{RED}●{GREEN}] {WHITE}ixBrowser Mode Completed: {s['checked']} Numbers")
            print(f" {GREEN}[{RED}●{GREEN}] {GREEN}Success: {s['success']}")
            print(f" {GREEN}[{RED}●{GREEN}] {RED}Failed: {s['failed']}")
            print(f"{LINE}")


if __name__ == "__main__":
    print(f"{CYAN}ixBrowser automation module — imported by ix_run.py{WHITE}")
    if not IXBROWSER_AVAILABLE:
        print(f"{RED}ixbrowser-local-api not installed.{WHITE}")
        sys.exit(1)
    print(f"{GREEN}Module loaded successfully.{WHITE}")
