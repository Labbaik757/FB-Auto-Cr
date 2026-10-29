"""Cookie extraction, STANDALONE. This mode has no relation to any
other mode: it reads ONLY a file of uids and passwords given for this
job, logs each already-created ID in with its password, extracts its
cookies, and saves uid|password|cookies into a separate output file.
It never reads any other mode's accounts file and imports no other
mode's code - only the project's shared infra (paths, colors).

Input: uid|password per line (extra fields, if any, are ignored -
every ID is freshly logged in, so input cookies are never used).
Default input file: output/cookie_input.txt - any path may be typed
at the prompt instead. If the input file does not exist, Mode 5
creates an empty one and asks you to fill it, instead of failing.
Output (fixed): output/cookies_output.txt.
Only successes are saved; the file is truncated at start and each
success is appended immediately, so partial progress survives an
interruption.

OTP during login: the visible browser WAITS there until the
user enters it in the browser. The moment the OTP scene is gone and
a session exists, the run continues automatically - no terminal input
is needed. A bare checkpoint page still skips the account with no retry.
An unsolved OTP challenge times out after 600s and the batch moves on.

NOTE: Meta's own verification handling is REMOVED completely
from this file. Meta asks for it for some IDs and not for others,
at its own discretion - that is Meta's behaviour, not a tool bug
to fix. The tool does not detect, wait for, or solve it, and it
does not appear in the challenge markers below. If Meta shows it,
that account simply does not complete in this run and the batch
moves on. A cookie set is only a success when BOTH c_user and xs
are present.
"""

import os
import random
import time

from playwright.sync_api import sync_playwright

from core.path_manager import get_base_storage_dir, get_output_dir
from ui.colors import CYAN, GREEN, RED, WHITE, YELLOW

CHALLENGE_MARKERS = (
    "login code", "two-factor",
    "approvals_code", "verification code", "enter the code",
    "confirm your identity",
)
CHALLENGE_TIMEOUT = 600
DEFAULT_INPUT = "output/cookie_input.txt"
DEFAULT_GAP = 60


def _pause(min_s, max_s):
    time.sleep(random.uniform(min_s, max_s))


def _type(page, selectors, text):
    """Type into the first selector that attaches. The login form's
    ids vary (and a page can load without the form at all, e.g. an
    error page), so a single hard selector must never raise and kill
    the batch. Returns True if typed, else False. Falls back to fill
    when click-typing is blocked by an overlay."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="attached", timeout=5000)
            try:
                el.click(timeout=5000)
                el.press_sequentially(text, delay=70)
            except Exception:
                el.fill(text, timeout=5000)
            return True
        except Exception:
            continue
    return False


def _click(page, locators):
    for loc in locators:
        try:
            loc.click(timeout=5000)
            return True
        except Exception:
            continue
    return False


def parse_input_file(path):
    """uid|password per line. Extra fields are ignored."""
    accounts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 2 or not parts[0].strip():
                continue
            accounts.append({"uid": parts[0].strip(),
                             "password": parts[1].strip()})
    return accounts


def serialize_cookies(cookies):
    """Header-style string: name=value pairs joined by '; '."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def _has_c_user(cookies):
    return any(c["name"] == "c_user" and c["value"] for c in cookies)


def _has_xs(cookies):
    """xs is the httpOnly session key. c_user alone is not a session:
    document.cookie returns c_user but never xs, so a cookie set
    without xs must never be saved as a success."""
    return any(c["name"] == "xs" and c["value"] for c in cookies)


def _body_text(page):
    try:
        return page.locator("body").inner_text().lower()
    except Exception:
        return ""


def _challenge_present(page):
    """OTP scene only. A bare checkpoint page (no OTP markers)
    is NOT a challenge - it skips. Meta's own verification is
    deliberately NOT detected here at all."""
    try:
        if page.locator('input[name="approvals_code"]').count() > 0:
            return True
    except Exception:
        pass
    text = _body_text(page)
    return any(m in text for m in CHALLENGE_MARKERS)


def _checkpoint(page):
    if "checkpoint" in page.url.lower():
        return True
    text = _body_text(page)
    return "checkpoint" in text or "confirm your identity" in text


EMAIL_SELECTORS = ["#email", "input[name='email']"]
PASS_SELECTORS = ["#pass", "input[name='pass']", "input[type='password']"]


def _login(page, uid, password):
    """Password login for one already-created ID. Raises RuntimeError
    if the login form never appears, so the caller can record that
    account as failed and continue with the next one."""
    page.goto("https://www.facebook.com/login", timeout=60000)
    _pause(1.0, 2.0)
    if not _type(page, EMAIL_SELECTORS, uid):
        raise RuntimeError("login form not found")
    _pause(0.5, 1.5)
    if not _type(page, PASS_SELECTORS, password):
        raise RuntimeError("login form not found")
    _pause(0.5, 1.0)
    _click(page, [
        page.get_by_role("button", name="Log in").first,
        page.locator("#loginbutton").first,
        page.locator('button[type="submit"]').first,
    ])
    _pause(2.0, 3.0)


def _ensure_input_file(path):
    """True if the input file already exists. If missing, create an
    empty one (plus parent dirs) and return False, so the caller can
    tell the user to fill it and rerun."""
    if os.path.exists(path):
        return True
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8"):
        pass
    return False


def run_cookie_mode():
    """Standalone cookie extraction. Returns result list."""
    raw = input(f"Input file (uid|password per line) "
                f"[{DEFAULT_INPUT}]: ").strip()
    in_path = raw or DEFAULT_INPUT
    if not os.path.isabs(in_path):
        in_path = os.path.join(get_base_storage_dir(), in_path)
    out_path = os.path.join(get_output_dir(), "cookies_output.txt")
    gap_raw = input(f"Gap between accounts in seconds (0-300) "
                    f"[{DEFAULT_GAP}]: ").strip()
    try:
        gap = int(gap_raw) if gap_raw else DEFAULT_GAP
    except ValueError:
        gap = DEFAULT_GAP
    gap = max(0, min(300, gap))
    if not _ensure_input_file(in_path):
        print(f"{YELLOW}Input file not found - created empty {in_path}. "
              f"Fill it with one uid|password per line, then run Mode 5 "
              f"again.{WHITE}")
        return []
    try:
        accounts = parse_input_file(in_path)
    except FileNotFoundError:
        print(f"{RED}Input file not found: {in_path}{WHITE}")
        return []
    if not accounts:
        print(f"{RED}No accounts in {in_path}{WHITE}")
        return []
    print(f"{CYAN}Cookie extraction: {len(accounts)} IDs from {in_path}, "
          f"output {out_path}{WHITE}")
    with open(out_path, "w", encoding="utf-8"):
        pass
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for i, account in enumerate(accounts):
                if i > 0:
                    time.sleep(gap)
                uid = account["uid"]
                ctx = browser.new_context()
                page = ctx.new_page()
                try:
                    _login(page, uid, account["password"])
                    start = time.time()
                    waited = False
                    res = None
                    while True:
                        cookies = ctx.cookies()
                        if (_has_c_user(cookies) and _has_xs(cookies)
                                and not _challenge_present(page)):
                            res = {"uid": uid, "ok": True,
                                   "cookies": serialize_cookies(cookies),
                                   "detail": "cookies extracted"}
                            break
                        if _challenge_present(page):
                            if not waited:
                                print(f"{YELLOW}[Cookie] Challenge in browser "
                                      f"for {uid} - solve it, waiting...{WHITE}")
                                waited = True
                            if time.time() - start > CHALLENGE_TIMEOUT:
                                res = {"uid": uid, "ok": False, "cookies": "",
                                       "detail": "challenge not solved in time "
                                               "- moved on"}
                                break
                            time.sleep(2)
                            continue
                        if _checkpoint(page):
                            res = {"uid": uid, "ok": False, "cookies": "",
                                   "detail": "checkpoint - skipped, no retry"}
                            break
                        if time.time() - start > 15:
                            res = {"uid": uid, "ok": False, "cookies": "",
                                   "detail": "login failed"}
                            break
                        time.sleep(2)
                except Exception as e:
                    # One account's unexpected failure must never kill
                    # the batch: record it and move to the next account.
                    res = {"uid": uid, "ok": False, "cookies": "",
                           "detail": f"login error: {e}"}
                finally:
                    ctx.close()
                res["password"] = account["password"]
                results.append(res)
                if res["ok"]:
                    with open(out_path, "a", encoding="utf-8") as f:
                        f.write(f"{res['uid']}|{res['password']}|"
                                f"{res['cookies']}\n")
                    print(f"{GREEN}[{uid}] cookies extracted{WHITE}")
                else:
                    print(f"{RED}[{uid}] {res['detail']}{WHITE}")
        finally:
            browser.close()
    done = sum(1 for r in results if r["ok"])
    print(f"{CYAN}Done: {done}/{len(results)} cookies saved to "
          f"{out_path}{WHITE}")
    return results
