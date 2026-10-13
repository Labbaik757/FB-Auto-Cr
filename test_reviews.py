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


def gemini_variations(reviews, needed, api_key):
    """Use Gemini to expand few reviews into many unique variations."""
    try:
        import google.generativeai as genai
    except ImportError:
        print(f"{YELLOW}Installing google-generativeai...{WHITE}")
        os.system(f"{sys.executable} -m pip install google-generativeai -q")
        import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    base = "\n".join([f"{i+1}. {r}" for i, r in enumerate(reviews)])
    prompt = f"""You are a review writer. Given these sample reviews:
{base}

Generate {needed} UNIQUE review variations. Same positive meaning, different wording each time.
Natural human tone, varied length (some short, some 2 sentences).
Output ONLY the reviews, one per line, no numbering."""

    resp = model.generate_content(prompt)
    lines = [l.strip() for l in resp.text.strip().split("\n") if l.strip()]
    # Clean numbering if present
    cleaned = []
    for l in lines:
        import re
        l = re.sub(r"^\d+[.\)]\s*", "", l)
        if l:
            cleaned.append(l)
    return cleaned[:needed]


def fb_login(context, page, cookie_str):
    """Login to Facebook directly via saved cookies (safer than password)."""
    try:
        cookies = []
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".facebook.com",
                "path": "/",
            })
        context.add_cookies(cookies)
    except Exception as e:
        with print_lock:
            print(f"{RED}[Reviews] Cookie load failed: {e}{WHITE}")
        return False
    # Verify by opening Facebook
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2.0, 3.0))
    try:
        url = page.url
        # Logged in = not on login page
        return "login" not in url
    except Exception:
        return False


def submit_review(page, page_url, review_text):
    """Navigate to page, open Reviews, select Yes, paste review, post.
    Returns True only if submission is verified."""
    page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
    _human_pause(2.0, 3.0)
    # Open Recommendations/Reviews dialog
    _opened = False
    for _sel in ['See Recommendations', 'Reviews', 'Recommendations']:
        try:
            _btn = page.get_by_role("button", name=_sel).first
            if _btn.count() > 0:
                _human_click(page, _btn)
                _opened = True
                with print_lock:
                    print(f"{CYAN}[Reviews] Opened via '{_sel}'{WHITE}")
                break
        except Exception:
            continue
    if not _opened:
        # Try aria-label variant
        try:
            _btn = page.locator('[aria-label="See Recommendations"]').first
            _human_click(page, _btn)
            _opened = True
        except Exception:
            pass
    if not _opened:
        with print_lock:
            print(f"{RED}[Reviews] Could not open recommendations dialog{WHITE}")
        return False
    _human_pause(2.0, 3.0)

    # Discover dialog UI: dump all radios/buttons in dialog
    with print_lock:
        print(f"{CYAN}[Reviews] Scanning dialog for Yes/No options...{WHITE}")
    _yes_clicked = False
    for _sel in ["Yes", "yes", "YES"]:
        for _role in ["radio", "button"]:
            try:
                _el = page.get_by_role(_role, name=_sel, exact=True).first
                if _el.count() > 0 and _el.is_visible(timeout=2000):
                    _human_click(page, _el)
                    _yes_clicked = True
                    with print_lock:
                        print(f"{GREEN}[Reviews] Clicked '{_sel}' ({_role}){WHITE}")
                    break
            except Exception:
                continue
        if _yes_clicked:
            break
    if not _yes_clicked:
        # Fallback: any element with exact text "Yes"
        try:
            _el = page.get_by_text("Yes", exact=True).first
            if _el.count() > 0 and _el.is_visible(timeout=2000):
                _human_click(page, _el)
                _yes_clicked = True
                with print_lock:
                    print(f"{GREEN}[Reviews] Clicked 'Yes' (text fallback){WHITE}")
        except Exception:
            pass
    if not _yes_clicked:
        # Last resort: dump what's actually in the dialog for debugging
        try:
            _dialog_text = page.locator('[role="dialog"]').first.inner_text()[:500]
            with print_lock:
                print(f"{YELLOW}[Reviews] Dialog contents: {_dialog_text}{WHITE}")
        except Exception:
            pass
        with print_lock:
            print(f"{RED}[Reviews] Yes option NOT FOUND - cannot proceed{WHITE}")
        return False
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
    submitted = False
    for btn_name in ["Post", "Submit", "Share"]:
        try:
            _human_click(page, page.get_by_role("button", name=btn_name).first)
            submitted = True
            break
        except Exception:
            continue
    if not submitted:
        with print_lock:
            print(f"{RED}[Reviews] Submit button not found{WHITE}")
        return False

    time.sleep(random.uniform(3.0, 5.0))

    # Verify: check if review appears or success message
    try:
        page_content = page.content().lower()
        if review_text[:20].lower() in page_content:
            with print_lock:
                print(f"{GREEN}[Reviews] Verified: review text found on page{WHITE}")
            return True
    except Exception:
        pass
    # If textbox is gone/empty, likely submitted
    try:
        textbox = page.get_by_role("textbox").first
        if textbox.input_value() == "":
            with print_lock:
                print(f"{GREEN}[Reviews] Verified: textbox cleared after post{WHITE}")
            return True
    except Exception:
        pass
    with print_lock:
        print(f"{YELLOW}[Reviews] Could not verify submission{WHITE}")
    return False


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

    # Ask how many reviews needed
    try:
        need = int(input(f"{CYAN}How many reviews needed? {WHITE}").strip())
    except Exception:
        need = len(reviews)

    # Gemini expands if needed > available
    if need > len(reviews):
        print(f"{CYAN}Need {need}, have {len(reviews)} - asking Gemini for variations...{WHITE}")
        _key_file = os.path.join(BASE, "gemini_api_key.txt")
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key and os.path.exists(_key_file):
            with open(_key_file) as _kf:
                api_key = _kf.read().strip()
        if not api_key:
            api_key = input(f"{CYAN}Enter Gemini API Key (one time only): {WHITE}").strip()
            if api_key:
                with open(_key_file, "w") as _kf:
                    _kf.write(api_key)
                print(f"{GREEN}API key saved - won't ask again{WHITE}")
        if api_key:
            reviews = gemini_variations(reviews, need, api_key)
            print(f"{GREEN}Gemini generated {len(reviews)} unique reviews{WHITE}")
        else:
            print(f"{YELLOW}No API key - using available reviews only{WHITE}")
            need = len(reviews)
    else:
        reviews = reviews[:need]

    # Live input: paste page link in terminal (like custom password)
    page_url = input(f"{CYAN}Paste Facebook Page Link and press Enter: {WHITE}").strip()
    if not page_url:
        print(f"{RED}No link given{WHITE}")
        return
    print(f"{CYAN}Page: {page_url}{WHITE}")
    print(f"{CYAN}Accounts: {len(accounts)}, Reviews: {len(reviews)}{WHITE}")

    # Pair accounts with reviews (test mode: max 2)
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
            uid = parts[0]
            cookie_str = parts[2] if len(parts) > 2 else ""
            if not cookie_str:
                print(f"{RED}[Reviews] No cookies for {uid}, skipping{WHITE}")
                continue
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
                if not fb_login(context, page, cookie_str):
                    print(f"{RED}[Reviews] Cookie login failed for {uid}{WHITE}")
                    continue
                print(f"{GREEN}[Reviews] Logged in via cookies: {uid}{WHITE}")

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
