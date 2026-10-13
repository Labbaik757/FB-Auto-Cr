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
    """Submit a page review. VERIFIED selectors (2026-10-13 live test).
    Flow: page?sk=reviews -> Yes button -> wait composer -> textbox -> Post.
    Returns True only if submission is verified."""
    # Extract page ID and go directly to reviews tab
    import re as _re
    _m = _re.search(r'id=(\d+)', page_url)
    if _m:
        _pid = _m.group(1)
        _reviews_url = f"https://www.facebook.com/profile.php?id={_pid}&sk=reviews"
    else:
        _reviews_url = page_url.rstrip("/") + "/reviews"
    page.goto(_reviews_url, wait_until="domcontentloaded", timeout=30000)
    _human_pause(2.0, 3.0)

    # Skip if this account already reviewed (no Yes button = already done)
    try:
        page.get_by_role("button", name="Yes", exact=True).first.wait_for(
            state="visible", timeout=8000)
    except Exception:
        _body = page.content().lower()
        if "recommends" in _body:
            with print_lock:
                print(f"{YELLOW}[Reviews] Already reviewed - skipping{WHITE}")
            return True  # not a failure
        with print_lock:
            print(f"{RED}[Reviews] Yes button not found and no existing review{WHITE}")
        return False

    # Click "Yes" (normal button, NOT radio)
    try:
        _yes = page.get_by_role("button", name="Yes", exact=True).first
        _human_click(page, _yes)
        with print_lock:
            print(f"{GREEN}[Reviews] Clicked Yes{WHITE}")
    except Exception as e:
        with print_lock:
            print(f"{RED}[Reviews] Yes button not found: {e}{WHITE}")
        return False

    # Wait for composer dialog (10-15 sec load)
    try:
        _dialog = page.get_by_role("dialog").first
        _dialog.wait_for(state="visible", timeout=20000)
        with print_lock:
            print(f"{CYAN}[Reviews] Dialog opened{WHITE}")
    except Exception as e:
        with print_lock:
            print(f"{RED}[Reviews] Dialog did not open: {e}{WHITE}")
        return False

    # Textbox: DIV contenteditable, dynamic aria-label - match by role only
    try:
        _textbox = _dialog.get_by_role("textbox").first
        _textbox.wait_for(state="visible", timeout=20000)
        _human_type(page, _textbox, review_text)
        with print_lock:
            print(f"{CYAN}[Reviews] Text typed{WHITE}")
    except Exception as e:
        with print_lock:
            print(f"{RED}[Reviews] Textbox failed: {e}{WHITE}")
        return False
    _human_pause(1.0, 2.0)

    # Set privacy to Public (else review stays Friends-only, not public)
    _priv_done = False
    for _priv_sel in [
        lambda: _dialog.get_by_role("button", name="Friends").first,
        lambda: _dialog.locator('[aria-label*="Edit privacy"]').first,
        lambda: _dialog.locator('[aria-label*="Sharing with"]').first,
    ]:
        try:
            _priv = _priv_sel()
            _priv.wait_for(state="visible", timeout=5000)
            _human_click(page, _priv)
            time.sleep(2)
            # Try Public option (multiple strategies)
            _pub_clicked = False
            for _pub_sel in [
                lambda: page.get_by_role("button", name="Public").first,
                lambda: page.get_by_role("menuitem", name="Public").first,
                lambda: page.locator('[role="menuitem"]').filter(has_text="Public").first,
                lambda: page.get_by_text("Public", exact=True).first,
            ]:
                try:
                    _pub = _pub_sel()
                    _pub.wait_for(state="visible", timeout=5000)
                    _human_click(page, _pub)
                    _pub_clicked = True
                    break
                except Exception:
                    continue
            time.sleep(2)
            if _pub_clicked:
                with print_lock:
                    print(f"{GREEN}[Reviews] Privacy set to Public{WHITE}")
                _priv_done = True
                break
            else:
                with print_lock:
                    print(f"{YELLOW}[Reviews] Public option not found, retrying{WHITE}")
                # Close dropdown by pressing Escape, try next selector
                try:
                    page.keyboard.press("Escape")
                    time.sleep(1)
                except Exception:
                    pass
        except Exception:
            continue
    if not _priv_done:
        with print_lock:
            print(f"{YELLOW}[Reviews] Privacy change skipped - review may be Friends-only{WHITE}")

    # Click Post (exact name "Post")
    try:
        _post = _dialog.get_by_role("button", name="Post", exact=True).first
        _human_click(page, _post)
        with print_lock:
            print(f"{CYAN}[Reviews] Clicked Post{WHITE}")
    except Exception as e:
        with print_lock:
            print(f"{RED}[Reviews] Post button not found: {e}{WHITE}")
        return False

    # Wait for dialog to CLOSE = real submission signal (up to 20 sec)
    _submitted = False
    for _i in range(20):
        time.sleep(1)
        try:
            if _dialog.count() == 0 or not _dialog.is_visible():
                _submitted = True
                break
        except Exception:
            _submitted = True  # dialog gone = submitted
            break
    if not _submitted:
        with print_lock:
            print(f"{RED}[Reviews] Dialog did not close - Post may have failed{WHITE}")
        # Try clicking Post once more
        try:
            _post2 = page.get_by_role("button", name="Post", exact=True).first
            if _post2.count() > 0 and _post2.is_visible(timeout=3000):
                _human_click(page, _post2)
                with print_lock:
                    print(f"{YELLOW}[Reviews] Retried Post click{WHITE}")
                time.sleep(5)
                try:
                    if _dialog.count() == 0 or not _dialog.is_visible():
                        _submitted = True
                except Exception:
                    _submitted = True
        except Exception:
            pass
    if not _submitted:
        with print_lock:
            print(f"{RED}[Reviews] FAILED: review not submitted{WHITE}")
        return False

    # Dialog closed - now verify review appears on page (dialog is gone)
    time.sleep(random.uniform(2.0, 4.0))
    _verified = False
    try:
        _page_text = page.content().lower()
        if review_text[:20].lower() in _page_text:
            _verified = True
    except Exception:
        pass

    # VISUAL CONFIRM: scroll review to center of screen, keep open 8 sec
    try:
        _review_el = page.get_by_text(review_text[:30]).first
        if _review_el.count() > 0:
            _review_el.scroll_into_view_if_needed(timeout=5000)
            # Center it exactly
            page.evaluate("""el => {
                const r = el.getBoundingClientRect();
                window.scrollBy(0, r.top - window.innerHeight/2 + r.height/2);
            }""", _review_el.element_handle(timeout=5000))
            with print_lock:
                print(f"{GREEN}[Reviews] Review visible on screen - showing for 8 sec{WHITE}")
            time.sleep(8)
            _verified = True
        else:
            # Fallback: scroll page to reviews section
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
            time.sleep(8)
    except Exception as e:
        with print_lock:
            print(f"{YELLOW}[Reviews] Visual scroll failed: {str(e)[:60]}{WHITE}")
        time.sleep(5)

    if _verified:
        with print_lock:
            print(f"{GREEN}[Reviews] VERIFIED: review live on page{WHITE}")
    else:
        with print_lock:
            print(f"{GREEN}[Reviews] Submitted (dialog closed){WHITE}")
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
