"""Cookie Extract (TEST VERSION) - login IDs, save uid+password+cookies.

Separate mode for one job only: read a file of uids and passwords,
log each ID in, extract its cookies, and save uid|password|cookies
lines into a SEPARATE file (output/browser_accounts_cookies.txt).
Cookie format matches browser_register exactly: name=value pairs
joined by "; ".

Cookie-first: an input line whose cookies are still valid is saved
without logging in. Otherwise password login runs. Only successes are
saved; failures are reported, never written as empty-cookie lines.

Captcha / OTP handling (user order): if a captcha or OTP scene
appears during login, the visible browser WAITS there until the user
solves it in the browser. The moment the challenge is gone and a
session exists, the run continues automatically - no terminal input
is needed. A bare checkpoint page (no captcha/OTP markers) still
skips the account with no retry (stand-down rule). An unsolved
challenge times out after 600 seconds and the batch moves on.

One account at a time, human behaviour throughout (shared helpers
from browser_register), a gap between accounts, one failure never
stops the batch.

TEST-VERSION HONESTY: the Facebook login selectors below are
best-effort and NOT live-verified yet. Run this mode on ONE account
first and report what breaks; every failure is reported honestly,
never faked as success.
"""

import os
import time

from playwright.sync_api import sync_playwright

from automation.browser_register import _human_pause, _human_type
from core.path_manager import get_base_storage_dir, get_output_dir
from ui.colors import CYAN, GREEN, RED, WHITE, YELLOW

FB_PROFILE_URL = "https://www.facebook.com/profile.php?id={uid}"
FB_LOGIN_URL = "https://www.facebook.com/login"
FB_DOMAIN = ".facebook.com"
CHALLENGE_TIMEOUT = 600

CHALLENGE_MARKERS = (
    "captcha", "security check", "login code", "two-factor",
    "approvals_code", "verification code", "enter the code",
    "not a robot",
)


# --- accounts file (format: uid|password|cookies, one per line) ---


def parse_accounts_file(path):
    accounts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 2:
                continue
            accounts.append({
                "uid": parts[0].strip(),
                "password": parts[1].strip(),
                "cookies": parts[2].strip() if len(parts) > 2 else "",
            })
    return accounts


def parse_cookie_string(raw, domain=FB_DOMAIN):
    """Accept JSON cookie list/dict, or 'name=value; name2=value2' text."""
    import json
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            return [{"name": c["name"], "value": c["value"],
                     "domain": c.get("domain", domain),
                     "path": c.get("path", "/")} for c in data]
        except Exception:
            return []
    out = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        out.append({"name": name.strip(), "value": value.strip(),
                    "domain": domain, "path": "/"})
    return out


def has_c_user(cookies):
    return any(c["name"] == "c_user" and c["value"] for c in cookies)


def serialize_cookies(cookies):
    """Header-style string, identical to browser_register's cookie_str."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


# --- challenge detection ---


def _visible_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return ""


def _challenge_present(page):
    """Captcha or OTP scene, visible on the page. A bare checkpoint
    page (no captcha/OTP markers) is NOT a challenge - it skips."""
    try:
        if page.locator('input[name="approvals_code"]').count() > 0:
            return True
    except Exception:
        pass
    text = _visible_text(page)
    return any(m in text for m in CHALLENGE_MARKERS)


# --- login with challenge wait ---


def _fill_login(page, uid, password):
    try:
        _human_type(page, "#email", uid)
        _human_pause(0.5, 1.5)
        _human_type(page, "#pass", password)
    except Exception:
        page.locator('input[name="email"]').fill(uid, timeout=10000)
        page.locator('input[name="pass"]').fill(password, timeout=10000)
    for locator in (
        page.get_by_role("button", name="Log in").first,
        page.locator('button[type="submit"]').first,
    ):
        try:
            locator.click(timeout=5000)
            return
        except Exception:
            continue


def login_with_wait(page, ctx, uid, password,
                    challenge_timeout=CHALLENGE_TIMEOUT):
    """Submit login. If a captcha/OTP scene appears, WAIT in the visible
    browser until the user solves it; the moment the challenge is gone
    and a session exists, continue automatically. Returns 'ok' |
    'checkpoint' | 'timeout' | 'failed' (with 'failed' also used for
    email-confirmation pages)."""
    page.goto(FB_LOGIN_URL, timeout=30000)
    _fill_login(page, uid, password)
    time.sleep(3)
    start = time.time()
    waited = False
    while True:
        url = page.url.lower()
        if has_c_user(ctx.cookies()) and not _challenge_present(page):
            return "ok"
        if _challenge_present(page):
            if not waited:
                print(f"{YELLOW}[Cookie] {uid}: captcha/OTP in browser - "
                      f"solve it, waiting...{WHITE}")
                waited = True
            if time.time() - start > challenge_timeout:
                return "timeout"
            time.sleep(2)
            continue
        if "checkpoint" in url:
            return "checkpoint"
        if "confirmemail" in url:
            return "failed"
        if time.time() - start > 15:
            return "failed"
        time.sleep(2)


# --- one account, end to end (single login) ---


def extract_for_account(pw, account, challenge_timeout=CHALLENGE_TIMEOUT):
    """One account. Returns dict(uid, ok, cookies, via, detail)."""
    uid = account["uid"]
    browser = pw.chromium.launch(headless=False)
    try:
        ctx = browser.new_context()
        cookies = parse_cookie_string(account.get("cookies", ""))
        if cookies:
            ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(FB_PROFILE_URL.format(uid=uid), timeout=30000)
        _human_pause(1.0, 2.0)
        via = "cookie"
        logged_in = has_c_user(ctx.cookies()) and \
            "checkpoint" not in page.url.lower() and \
            "confirmemail" not in page.url.lower()
        if not logged_in:
            via = "password"
            status = login_with_wait(page, ctx, uid, account["password"],
                                     challenge_timeout)
            if status == "checkpoint":
                return {"uid": uid, "ok": False, "cookies": "",
                        "via": via, "detail": "checkpoint - skipped, no retry"}
            if status == "timeout":
                return {"uid": uid, "ok": False, "cookies": "",
                        "via": via,
                        "detail": "challenge not solved in time - moved on"}
            if status != "ok":
                return {"uid": uid, "ok": False, "cookies": "",
                        "via": via, "detail": "login failed"}
            page.goto(FB_PROFILE_URL.format(uid=uid), timeout=30000)
            _human_pause(1.0, 2.0)
            if not has_c_user(ctx.cookies()):
                return {"uid": uid, "ok": False, "cookies": "",
                        "via": via, "detail": "login failed"}
        return {"uid": uid, "ok": True,
                "cookies": serialize_cookies(ctx.cookies()),
                "via": via, "detail": "cookies extracted"}
    finally:
        browser.close()


# --- interactive entry (main.py Mode 5) ---


def run_cookie_mode():
    print(f"{CYAN}=== Cookie Extract (test version) ==={WHITE}")
    out_dir = get_output_dir()
    default_in = os.path.join(out_dir, "browser_accounts.txt")
    typed = input(
        f"{CYAN}Input file (uid|password per line) "
        f"[{default_in}] {WHITE}").strip()
    in_path = typed or default_in
    if not os.path.isabs(in_path):
        in_path = os.path.join(get_base_storage_dir(), in_path)
    if not os.path.exists(in_path):
        print(f"{RED}Input file not found: {in_path}{WHITE}")
        return
    accounts = parse_accounts_file(in_path)
    if not accounts:
        print(f"{RED}No accounts in {in_path}{WHITE}")
        return
    out_path = os.path.join(out_dir, "browser_accounts_cookies.txt")
    print(f"{CYAN}Found {len(accounts)} account(s). Cookies will be saved "
          f"to {out_path}{WHITE}")
    print(f"{YELLOW}Captcha/OTP scenes pause the browser for your manual "
          f"solve (up to {CHALLENGE_TIMEOUT}s); the run continues "
          f"automatically once solved.{WHITE}")
    gap_raw = input(
        f"{CYAN}Gap between accounts in seconds [60] {WHITE}").strip()
    try:
        gap = max(0, min(300, int(gap_raw))) if gap_raw else 60
    except ValueError:
        gap = 60
    with open(out_path, "w", encoding="utf-8"):
        pass
    ok_count = 0
    failed = 0
    with sync_playwright() as pw:
        for i, account in enumerate(accounts):
            if i > 0:
                time.sleep(gap)
            res = extract_for_account(pw, account)
            label = account["uid"]
            if res["ok"]:
                ok_count += 1
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(f"{res['uid']}|{account['password']}|"
                            f"{res['cookies']}\n")
                print(f"{GREEN}[Cookie] {label}: saved via "
                      f"{res['via']}{WHITE}")
            else:
                failed += 1
                print(f"{RED}[Cookie] {label}: FAILED - "
                      f"{res['detail']}{WHITE}")
    print(f"{CYAN}Done: saved {ok_count}, failed {failed}. "
          f"Output: {out_path}{WHITE}")
