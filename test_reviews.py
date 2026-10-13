"""Test: Fb Reviews Automation (2 accounts, 2 reviews).
Run: python test_reviews.py

Reads:
  output/browser_accounts.txt  (uid|password|cookies)
  reviews.txt                  (one review per line - paste client list here)
  target_page.txt              (Facebook page URL)

Separate test - does NOT touch main tool.
"""
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from automation.browser_register import (
    _apply_fingerprint_spoof,
    _human_type,
    _human_pause,
    _human_click,
    _launch_browser,
)
from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN
from ui.display import print_lock

BASE = os.path.dirname(os.path.abspath(__file__))


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]


def fb_login(page, uid, password):
    """Login to Facebook with uid/email + password."""
    page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
    _human_pause(1.0, 2.0)
    try:
        page.get_by_label("Email or phone").fill(uid)
    except Exception:
        page.locator('input[name="email"]').fill(uid)
    _human_pause(0.5, 1.0)
    try:
        page.get_by_label("Password").fill(password)
    except Exception:
        page.locator('input[name="pass"]').fill(password)
    _human_pause(0.5, 1.0)
    try:
        page.get_by_role("button", name="Log in", exact=True).click()
    except Exception:
        page.keyboard.press("Enter")
    # Wait for login (feed or checkpoint)
    for _ in range(20):
        try:
            url = page.url
            if "login" not in url or "checkpoint" in url:
                break
        except Exception:
            pass
        time.sleep(1.0)
    time.sleep(random.uniform(2.0, 3.0))
    return "checkpoint" not in page.url


def submit_review(page, page_url, review_text, stars=5):
    """Navigate to page, open Reviews, submit star rating + text."""
    page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
    _human_pause(2.0, 3.0)
    # Go to Reviews tab
    try:
        page.get_by_role("link", name="Reviews").first.click(timeout=5000)
    except Exception:
        # Try URL-based reviews page
        base = page_url.rstrip("/")
        page.goto(base + "/reviews", wait_until="domcontentloaded", timeout=30000)
    _human_pause(2.0, 3.0)
    # Click star rating
    try:
        stars_btn = page.get_by_role("button", name=f"{stars} star").first
        _human_click(page, stars_btn)
    except Exception:
        with print_lock:
            print(f"{YELLOW}[Reviews] Star button not found, trying generic{WHITE}")
    _human_pause(1.0, 2.0)
    # Write review text
    try:
        textbox = page.get_by_role("textbox").first
        _human_type(page, textbox, review_text)
    except Exception as e:
        with print_lock:
            print(f"{RED}[Reviews] Textbox failed: {e}{WHITE}")
        return False
    _human_pause(1.0, 2.0)
    # Submit
    try:
        _human_click(page, page.get_by_role("button", name="Post").first)
    except Exception:
        try:
            _human_click(page, page.get_by_role("button", name="Submit").first)
        except Exception as e:
            with print_lock:
                print(f"{RED}[Reviews] Submit failed: {e}{WHITE}")
            return False
    time.sleep(random.uniform(2.0, 4.0))
    return True


def main():
    print(f"{CYAN}=== Fb Reviews Automation TEST ==={WHITE}")

    accounts = read_lines(os.path.join(BASE, "output", "browser_accounts.txt"))
    reviews = read_lines(os.path.join(BASE, "reviews.txt"))

    if not accounts:
        print(f"{RED}No accounts in output/browser_accounts.txt{WHITE}")
        return
    if not reviews:
        print(f"{RED}No reviews in reviews.txt - paste client list there{WHITE}")
        return

    # Live input: paste page link in terminal (like custom password)
    page_url = input(f"{CYAN}Paste Facebook Page Link and press Enter: {WHITE}").strip()
    if not page_url:
        print(f"{RED}No link given{WHITE}")
        return
    print(f"{CYAN}Page: {page_url}{WHITE}")
    print(f"{CYAN}Accounts: {len(accounts)}, Reviews: {len(reviews)}{WHITE}")

    # Test with first 2 accounts
    test_pairs = list(zip(accounts[:2], reviews[:2]))

    with sync_playwright() as p:
        _exe = os.path.expandvars(
            r"C:\Users\Rizvi Lion\AppData\Local\ms-playwright\chromium-1243\chrome-win\chrome.exe"
        )
        _launch_kwargs = dict(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        browser = _launch_browser(p, _launch_kwargs, _exe)

        done = 0
        for acc_line, review in test_pairs:
            parts = acc_line.split("|")
            uid, password = parts[0], parts[1]
            print(f"\n{CYAN}--- Account: {uid} ---{WHITE}")

            _vp = random.choice([(1366, 768), (1920, 1080), (1536, 864)])
            _cv = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0"])
            _ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_cv} Safari/537.36"
            context = browser.new_context(
                viewport={"width": _vp[0], "height": _vp[1]},
                user_agent=_ua,
                locale="en-US",
            )
            _apply_fingerprint_spoof(context, _cv, _vp)
            page = context.new_page()

            try:
                if not fb_login(page, uid, password):
                    print(f"{RED}[Reviews] Login failed for {uid}{WHITE}")
                    continue
                print(f"{GREEN}[Reviews] Logged in: {uid}{WHITE}")

                if submit_review(page, page_url, review):
                    print(f"{GREEN}[Reviews] Review submitted for {uid}{WHITE}")
                    done += 1
                else:
                    print(f"{RED}[Reviews] Review FAILED for {uid}{WHITE}")
            except Exception as e:
                print(f"{RED}[Reviews] Error for {uid}: {e}{WHITE}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                time.sleep(random.uniform(3.0, 5.0))

        browser.close()
        print(f"\n{CYAN}{'='*50}{WHITE}")
        print(f"{GREEN}[Reviews] TEST DONE: {done}/{len(test_pairs)} reviews submitted{WHITE}")
        print(f"{CYAN}{'='*50}{WHITE}")


if __name__ == "__main__":
    main()
