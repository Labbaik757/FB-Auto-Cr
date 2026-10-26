"""DP Apply (TEST VERSION) - profile pictures for IDs without a DP.

Run via main.py modes 2 and 3. Reads output/browser_accounts.txt (the same
file every mode writes/reads through core.path_manager), opens each
account, and applies a photorealistic DP only where the ID has none.
IDs that already have a DP are skipped, never overwritten.

One account at a time, human behaviour throughout (shared helpers from
browser_register), a gap between accounts, one failure never stops the
batch, a checkpoint skips the account with no retry (stand-down rule).

TEST-VERSION HONESTY: the Facebook dialog selectors below are
best-effort and NOT live-verified yet. Run it from Mode 2 or Mode 3 on ONE account first
and report what breaks; every failure is reported honestly, never
faked as success. The Pollinations key comes from the
POLLINATIONS_API_KEY environment variable, never from the repo.
"""

import os
import time

from playwright.sync_api import sync_playwright

from automation.browser_register import (
    _human_click,
    _human_pause,
    _human_type,
)
from automation.dp_generate import build_prompt, generate_png
from core.path_manager import get_output_dir
from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN

FB_PROFILE_URL = "https://www.facebook.com/profile.php?id={uid}"
FB_LOGIN_URL = "https://www.facebook.com/login"

# A custom photo is served from Facebook's user-content CDN. Default
# avatars come from the static CDN or carry one of these markers. Any
# unrecognised picture URL is treated as custom (skip = safe: missing
# one DP is harmless, overwriting an existing DP is not).
DEFAULT_DP_MARKERS = ("silhouette", "static.xx", "empty-profile", "default")


# --- accounts file (format: uid|password|cookies, one per line) ---


def parse_accounts_file(path):
    accounts = []
    if not os.path.exists(path):
        return accounts
    with open(path, "r", encoding="utf-8") as f:
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


def parse_cookie_string(raw, domain):
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


# --- profile reading ---


def read_profile_name(page):
    try:
        el = page.locator("h1").first
        if el.count() and el.inner_text(timeout=5000).strip():
            return el.inner_text(timeout=5000).strip()
    except Exception:
        pass
    return ""


def _pic_locator(page):
    """First locator that finds the profile picture image, else None."""
    candidates = [
        page.locator('img[alt="Profile picture"]').first,
        page.get_by_role("img", name="Profile picture").first,
        page.locator('a[aria-label="Profile picture"] img').first,
        page.locator('div[aria-label="Profile picture"] img').first,
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


def _pic_src(page):
    loc = _pic_locator(page)
    if loc is None:
        return None
    try:
        return loc.get_attribute("src", timeout=5000)
    except Exception:
        return None


def has_custom_dp(page):
    """True if the profile already has a custom picture, False if the
    picture is a default avatar (i.e. the ID has no DP yet)."""
    src = _pic_src(page)
    if not src:
        return False
    low = src.lower()
    if "scontent" in low:
        return True
    if any(m in low for m in DEFAULT_DP_MARKERS):
        return False
    return True  # unrecognised URL: skip is the safe side


# --- DP upload on one open profile page ---


def _try_click(page, locators):
    """Click the first locator that is present; False if none worked."""
    for loc in locators:
        try:
            if loc.count() > 0 and loc.is_visible():
                _human_click(page, loc)
                return True
        except Exception:
            continue
    return False


def apply_dp_on_page(page, photo_path):
    """Assumes page is already on the account's own profile, logged in.
    Returns dict(ok, detail). Every step is condition-based; a missing
    control is an honest failure, never a faked success."""
    before = _pic_src(page)
    if before is None:
        return {"ok": False, "detail": "profile picture element not found"}
    # Open the picture editor: edit button first, else the picture itself.
    opened = _try_click(page, [
        page.get_by_role("button", name="Edit profile picture").first,
        page.get_by_role("button", name="Update profile picture").first,
        _pic_locator(page),
    ])
    if not opened:
        return {"ok": False, "detail": "edit control not found"}
    _human_pause(1.0, 2.0)
    # Choose upload inside the dialog/menu.
    if not _try_click(page, [
        page.get_by_role("button", name="Upload photo").first,
        page.get_by_role("button", name="Update profile picture").first,
    ]):
        return {"ok": False, "detail": "upload control not found"}
    _human_pause(1.0, 2.0)
    # Attach the file (hidden input pattern, same as marketplace upload).
    try:
        page.locator('input[type="file"]').first.set_input_files(
            photo_path, timeout=15000)
    except Exception:
        try:
            with page.expect_file_chooser(timeout=10000) as fc:
                _try_click(page, [
                    page.get_by_role("button", name="Upload photo").first])
            fc.value.set_files(photo_path, timeout=15000)
        except Exception as e:
            return {"ok": False, "detail": f"file attach failed: {e}"}
    _human_pause(1.0, 2.0)
    # Save / confirm.
    if not _try_click(page, [
        page.get_by_role("button", name="Save", exact=True).first,
        page.get_by_role("button", name="Crop and save").first,
        page.get_by_role("button", name="Done").first,
    ]):
        return {"ok": False, "detail": "save button not found"}
    # Verify: the picture URL must actually change.
    for _ in range(15):
        time.sleep(1)
        after = _pic_src(page)
        if after and after != before:
            return {"ok": True, "detail": "profile picture changed"}
    return {"ok": False, "detail": "picture did not change after save"}


def password_login(page, uid, password):
    """Fill the login form. Returns 'checkpoint' or 'submitted'.
    The caller verifies the session via the c_user cookie."""
    try:
        page.goto(FB_LOGIN_URL, timeout=30000)
        try:
            _human_type(page, "#email", uid)
            _human_pause(0.5, 1.5)
            _human_type(page, "#pass", password)
        except Exception:
            page.locator('input[name="email"]').fill(uid, timeout=10000)
            page.locator('input[name="pass"]').fill(password, timeout=10000)
        _try_click(page, [
            page.get_by_role("button", name="Log in").first,
            page.get_by_role("button", name="login").first,
            page.locator('button[type="submit"]').first,
        ])
        page.wait_for_timeout(3000)
        if "checkpoint" in page.url.lower():
            return "checkpoint"
        return "submitted"
    except Exception:
        return "submitted"


# --- one account, end to end (single login) ---


def _seed_for(uid):
    if uid.isdigit():
        return int(uid) % 1000000
    return sum(uid.encode()) % 1000000


def process_account(pw, account, api_key, dp_dir, headless=False):
    """Login -> read name -> skip if DP exists -> else generate + apply.
    Returns dict(uid, name, ok, skipped, via, detail)."""
    uid = account["uid"]
    browser = pw.chromium.launch(headless=headless,
                                 args=["--no-sandbox"])
    try:
        ctx = browser.new_context()
        cookies = parse_cookie_string(account.get("cookies", ""),
                                      "facebook.com")
        if cookies:
            ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(FB_PROFILE_URL.format(uid=uid), timeout=30000)
        _human_pause(1.0, 2.0)
        via = "cookie"
        logged_in = has_c_user(ctx.cookies()) and bool(
            read_profile_name(page))
        if not logged_in:
            # Cookie dead (common for old IDs) -> password fallback.
            via = "password"
            status = password_login(page, uid, account["password"])
            if status == "checkpoint":
                return {"uid": uid, "name": "", "ok": False,
                        "skipped": False, "via": via,
                        "detail": "checkpoint - skipped, no retry"}
            page.goto(FB_PROFILE_URL.format(uid=uid), timeout=30000)
            _human_pause(1.0, 2.0)
            if not (has_c_user(ctx.cookies())
                    and bool(read_profile_name(page))):
                return {"uid": uid, "name": "", "ok": False,
                        "skipped": False, "via": via,
                        "detail": "login failed"}
        name = read_profile_name(page)
        if has_custom_dp(page):
            return {"uid": uid, "name": name, "ok": True, "skipped": True,
                    "via": via, "detail": "already has DP - skipped"}
        prompt = build_prompt(name or f"User {uid}", "", _seed_for(uid))
        gen = generate_png(prompt,
                           os.path.join(dp_dir, uid),
                           seed=_seed_for(uid), api_key=api_key)
        if not gen["ok"]:
            return {"uid": uid, "name": name, "ok": False,
                    "skipped": False, "via": via,
                    "detail": f"generation failed: {gen['error']}"}
        res = apply_dp_on_page(page, gen["path"])
        res["uid"] = uid
        res["name"] = name
        res["via"] = via
        res["skipped"] = False
        return res
    finally:
        browser.close()


# --- interactive entry (main.py modes 2 and 3) ---


def run_dp_mode():
    print(f"{CYAN}=== DP Apply (test version) ==={WHITE}")
    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if not api_key:
        print(f"{RED}POLLINATIONS_API_KEY is not set.{WHITE}")
        print(f"{YELLOW}Get a free key at enter.pollinations.ai, set it "
              f"as an environment variable, then run Mode 2 or Mode 3 again.{WHITE}")
        return
    accounts = parse_accounts_file(
        os.path.join(get_output_dir(), "browser_accounts.txt"))
    if not accounts:
        print(f"{RED}No accounts in output/browser_accounts.txt{WHITE}")
        return
    print(f"{CYAN}Found {len(accounts)} account(s). "
          f"Only IDs without a DP will get one.{WHITE}")
    try:
        gap = int(input(
            f"{CYAN}Gap between accounts in seconds [60] {WHITE}"
        ).strip() or "60")
    except Exception:
        gap = 60
    gap = max(0, min(gap, 300))
    dp_dir = os.path.join(get_output_dir(), "dp")
    os.makedirs(dp_dir, exist_ok=True)
    applied = skipped = failed = 0
    with sync_playwright() as pw:
        for i, account in enumerate(accounts):
            if i > 0:
                time.sleep(gap)
            res = process_account(pw, account, api_key, dp_dir,
                                  headless=False)
            label = res.get("name") or res["uid"]
            if res.get("skipped"):
                skipped += 1
                print(f"{YELLOW}[DP] {label}: skipped - {res['detail']}"
                      f"{WHITE}")
            elif res["ok"]:
                applied += 1
                print(f"{GREEN}[DP] {label}: applied via {res['via']}"
                      f"{WHITE}")
            else:
                failed += 1
                print(f"{RED}[DP] {label}: FAILED - {res['detail']}"
                      f"{WHITE}")
    print(f"{CYAN}Done: applied {applied}, skipped {skipped}, "
          f"failed {failed}. DPs saved in {dp_dir}{WHITE}")
