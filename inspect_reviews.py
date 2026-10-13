"""Inspect: Dump Facebook Page review UI structure.
Run: python inspect_reviews.py
Paste page link when asked. Uses first account's cookies.
Prints all buttons, radios, textboxes visible on reviews page.
"""
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from automation.browser_register import _apply_fingerprint_spoof, _launch_browser, _human_pause
from ui.colors import GREEN, RED, WHITE, CYAN
from ui.display import print_lock

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    print(f"{CYAN}=== Review UI Inspector ==={WHITE}")

    # Live cookie paste (like custom password)
    print(f"{CYAN}Paste Facebook cookies (c_user=...; xs=...; etc) and press Enter:{WHITE}")
    cookie_str = input().strip()
    if not cookie_str:
        # Fallback: first account from file
        acc_path = os.path.join(BASE, "output", "browser_accounts.txt")
        with open(acc_path) as f:
            accounts = [l.strip() for l in f if l.strip()]
        parts = accounts[0].split("|")
        cookie_str = parts[2] if len(parts) > 2 else ""
        print(f"{CYAN}Using saved cookies from file{WHITE}")

    page_url = input(f"{CYAN}Paste Facebook Page Link: {WHITE}").strip()

    with sync_playwright() as p:
        _exe = os.path.expandvars(
            r"C:\Users\Rizvi Lion\AppData\Local\ms-playwright\chromium-1243\chrome-win\chrome.exe"
        )
        browser = _launch_browser(p, dict(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        ), _exe)

        context = browser.new_context(viewport={"width": 1366, "height": 768}, locale="en-US")
        # Load cookies
        cookies = []
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            cookies.append({"name": name.strip(), "value": value.strip(),
                            "domain": ".facebook.com", "path": "/"})
        context.add_cookies(cookies)
        page = context.new_page()

        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        print(f"{GREEN}Logged in: {'login' not in page.url}{WHITE}")

        # Go to reviews
        page.goto(page_url.rstrip("/") + "/reviews", wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        print(f"\n{CYAN}=== BUTTONS ==={WHITE}")
        try:
            for b in page.get_by_role("button").all()[:30]:
                try:
                    print(f"  BTN: '{b.inner_text()[:50]}' | aria='{b.get_attribute('aria-label')}'")
                except Exception:
                    pass
        except Exception as e:
            print(f"  Error: {e}")

        print(f"\n{CYAN}=== RADIOS ==={WHITE}")
        try:
            for r in page.get_by_role("radio").all()[:20]:
                try:
                    print(f"  RADIO: '{r.inner_text()[:50]}' | aria='{r.get_attribute('aria-label')}' | name='{r.get_attribute('name')}'")
                except Exception:
                    pass
        except Exception as e:
            print(f"  Error: {e}")

        print(f"\n{CYAN}=== TEXTBOXES ==={WHITE}")
        try:
            for t in page.get_by_role("textbox").all()[:10]:
                try:
                    print(f"  TEXTBOX: placeholder='{t.get_attribute('placeholder')}' | aria='{t.get_attribute('aria-label')}'")
                except Exception:
                    pass
        except Exception as e:
            print(f"  Error: {e}")

        print(f"\n{CYAN}=== LINKS (Reviews etc) ==={WHITE}")
        try:
            for l in page.get_by_role("link").all()[:30]:
                try:
                    txt = l.inner_text()[:40]
                    if txt.strip():
                        print(f"  LINK: '{txt}'")
                except Exception:
                    pass
        except Exception as e:
            print(f"  Error: {e}")

        print(f"\n{GREEN}Browser open for 60s - inspect manually if needed{WHITE}")
        time.sleep(60)
        browser.close()


if __name__ == "__main__":
    main()
