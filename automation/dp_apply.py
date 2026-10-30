"""DP Apply (TEST VERSION) - profile pictures for IDs without a DP.

Run via main.py mode 5. Reads output/browser_accounts.txt (the same
file every mode writes/reads through core.path_manager), opens each
account, and applies a photorealistic DP only where the ID has none.
IDs that already have a DP are skipped, never overwritten.

One account at a time, human behaviour throughout (shared helpers from
browser_register), a gap between accounts, one failure never stops the
batch, a checkpoint skips the account with no retry (stand-down rule).

TEST-VERSION HONESTY, UPDATED 2026-10-29: the DP upload selectors
below were LIVE-VERIFIED on a real ID (Sophia Wilson) on 2026-10-29:
Profile picture actions -> Choose profile picture -> file input
index 3 -> crop dialog -> Save, verified by the profile picture
changing and by the "updated profile picture" timeline post.
Pollinations setup: key set -> keyed gen endpoint; no key ->
anonymous legacy endpoint (shared pool). The key comes only from
POLLINATIONS_API_KEY, never from the repo.
"""

import os
import time

from playwright.sync_api import sync_playwright

from automation.browser_register import (
    _human_click,
    _human_pause,
    _human_type,
)
from automation.dp_generate import (
    JPEG_MAGIC,
    PNG_MAGIC,
    build_prompt,
    generate_png,
)
from automation.captcha_solver import detect_gate, solve_recaptcha
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


def _is_logged_in(page, ctx):
    """True only for a real logged-in session. Cookie presence alone
    proves nothing: dead cookies stay in the jar, and a logged-out
    profile page still shows the person's name in h1 - so the old
    check (c_user + name) passed for dead sessions and the password
    fallback never ran. A logged-out page always shows a Log in
    control; a logged-in session never does - that is the
    discriminator."""
    if not has_c_user(ctx.cookies()):
        return False
    if not read_profile_name(page):
        return False
    for role in ("link", "button"):
        try:
            if page.get_by_role(role, name="Log in").first.is_visible():
                return False
        except Exception:
            pass
    return True


# --- profile reading ---


def read_profile_name(page):
    try:
        el = page.locator("h1").first
        if el.count() and el.inner_text(timeout=5000).strip():
            return el.inner_text(timeout=5000).strip()
    except Exception:
        pass
    return ""


def _pic_candidates(page):
    return [
        page.locator('img[alt="Profile picture"]').first,
        page.get_by_role("img", name="Profile picture").first,
        page.locator('a[aria-label="Profile picture"] img').first,
        page.locator('div[aria-label="Profile picture"] img').first,
    ]


def _pic_locator(page):
    """First locator that finds the profile picture image, else None."""
    for loc in _pic_candidates(page):
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


def _wait_for_pic(page):
    """Wait until some profile-picture candidate attaches. FB renders
    the header asynchronously; an instant count() misses a picture that
    is still loading. True if found, else False."""
    for loc in _pic_candidates(page):
        try:
            loc.wait_for(state="attached", timeout=5000)
            return True
        except Exception:
            continue
    return False


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


def _js_click_by_text(page, exact_text):
    """JS-click the element whose rendered text is exactly exact_text.
    Playwright role clicks time out on this dialog because the dialog
    overlay intercepts them; a JS click does not. Matches on innerText
    (rendered text), NOT textContent: Facebook obfuscates textContent
    with combining characters, so exact textContent matches fail on
    live pages. Prefers a role=menuitem/button match, else the last
    (deepest) match - nested ancestors share the rendered text of the
    clickable leaf. Returns True if an element was clicked, else
    False. LIVE 2026-10-30: the crop dialog is rendered TWICE in the
    DOM (two identical Save buttons at the same coordinates) - the
    first match is the stale duplicate, so the last match must be
    used."""
    try:
        return page.evaluate("""(text) => {
            const els = [...document.querySelectorAll('*')]
                .filter(e => (e.innerText || '').trim() === text);
            if (!els.length) return false;
            const role = els.find(e => ['menuitem', 'button']
                .includes(e.getAttribute('role')));
            (role || els[els.length - 1]).click(); return true;
        }""", exact_text)
    except Exception:
        return False


def _js_click_save(page):
    """Click the crop dialog's Save button. Facebook renders the
    dialog twice in the DOM (two identical role=button Save buttons
    at the same coordinates); the first is a stale duplicate whose
    click does nothing visible, so the LAST match must be clicked.
    Matches on innerText, not textContent (obfuscated on live pages).
    Prefers a div[role=button] with exact text Save, last in DOM."""
    try:
        return page.evaluate("""() => {
            const els = [...document.querySelectorAll('div[role="button"]')]
                .filter(e => (e.innerText || '').trim() === 'Save');
            if (els.length) { els[els.length - 1].click(); return true; }
            const any = [...document.querySelectorAll('*')]
                .filter(e => (e.innerText || '').trim() === 'Save');
            if (any.length) { any[any.length - 1].click(); return true; }
            return false;
        }""")
    except Exception:
        return False


def _js_click_profile_actions(page):
    """JS-click the first element with aria-label
    'Profile picture actions'. Returns True if clicked."""
    try:
        return page.evaluate("""() => {
            const el = [...document.querySelectorAll('[aria-label]')]
                .find(e => e.getAttribute('aria-label')
                           === 'Profile picture actions');
            if (el) { el.click(); return true; }
            return false;
        }""")
    except Exception:
        return False


def _wait_for_text(page, exact_text, timeout_s=10):
    """Poll until an element with the exact rendered text exists.
    The menu/dialog renders slowly on throttled connections - a fixed
    1-2s pause is not enough (live 2026-10-30: the actions menu took
    ~3s to appear after the click). Returns True if found."""
    for _ in range(timeout_s * 2):
        try:
            n = page.evaluate("""(text) => [...document.querySelectorAll('*')]
                .filter(e => (e.innerText || '').trim() === text).length""",
                exact_text)
            if n:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def apply_dp_on_page(page, photo_path):
    """Assumes page is already on the account's own profile, logged in.
    Returns dict(ok, detail). Live-verified flow 2026-10-29,
    CORRECTED 2026-10-30: Profile picture actions -> Choose profile
    picture -> file input index 3 (the profile-picture input; index
    0 is the cover trap and must never be used) -> crop dialog ->
    Save (LAST role=button match - the dialog is rendered twice in
    the DOM). Every step is condition-based; a missing control is an
    honest failure, never a faked success. The before-picture is NOT
    a gate: on some loads the header DP image is not rendered at all
    (no alt="Profile picture" img in the DOM) while the actions
    trigger still exists - so a missing before-src no longer fails
    the run; success is then the "Your profile picture has been
    updated" toast, or a changed picture URL."""
    before = _pic_src(page)
    if not _js_click_profile_actions(page):
        return {"ok": False, "detail": "profile picture actions not found"}
    # The menu renders slowly on throttled connections: poll for it
    # instead of a fixed short pause.
    if not _wait_for_text(page, "Choose profile picture", timeout_s=10):
        return {"ok": False, "detail": "choose profile picture not found"}
    if not _js_click_by_text(page, "Choose profile picture"):
        return {"ok": False, "detail": "choose profile picture not found"}
    _human_pause(1.0, 2.0)
    # Attach the file to input index 3 only. The page holds 4 file
    # inputs in DOM order; index 3 is the image-only profile-picture
    # input. Index 0 sets a cover draft by mistake - never use it,
    # and never fall back to the first input on failure.
    try:
        inputs = page.locator('input[type="file"]')
        # The 4th (profile) input renders with the crop dialog: poll
        # for it instead of an instant count (live 2026-10-30: only 3
        # inputs were present right after the Choose click).
        for _ in range(20):
            if inputs.count() >= 4:
                break
            time.sleep(0.5)
        if inputs.count() < 4:
            return {"ok": False,
                    "detail": "profile file input not found "
                              f"(only {inputs.count()} file inputs)"}
        inputs.nth(3).set_input_files(photo_path, timeout=15000)
    except Exception as e:
        return {"ok": False, "detail": f"file attach failed: {e}"}
    # The crop dialog also renders slowly: poll for Save before
    # clicking it.
    if not _wait_for_text(page, "Save", timeout_s=10):
        return {"ok": False, "detail": "save button not found"}
    # Save / confirm in the crop dialog (JS click: role click is
    # intercepted by the dialog overlay, same as Choose above).
    # The dialog is rendered twice: click the LAST Save button.
    if not _js_click_save(page):
        return {"ok": False, "detail": "save button not found"}
    # Verify: the toast proves the save, or the picture URL changes.
    # The crop dialog may stay visible as a stale duplicate after
    # the toast - the toast is the proof, not the dialog closing.
    # Poll up to 15s for either signal.
    for _ in range(15):
        time.sleep(1)
        try:
            body = page.evaluate(
                "() => document.body.innerText.slice(0, 4000)")
        except Exception:
            body = ""
        if "Your profile picture has been updated" in body:
            return {"ok": True, "detail": "profile picture changed"}
        after = _pic_src(page)
        if before and after and after != before:
            return {"ok": True, "detail": "profile picture changed"}
    return {"ok": False, "detail": "picture did not change after save"}


def password_login(page, uid, password):
    """Fill the login form. Returns 'checkpoint', 'submitted', or
    'captcha-unavailable' (a reCAPTCHA gate appeared and the solver
    could not run - the caller must report that, not a bare
    'login failed'). The caller verifies the session via the
    c_user cookie. A reCAPTCHA gate on an old ID is solved by
    automation/captcha_solver (Gemini vision, no hard-coded
    answers); if it cannot run, the gate is left for the user in
    the visible browser."""
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
        if detect_gate(page) == "recaptcha":
            solved = solve_recaptcha(page, ctx=None)
            if not solved["ok"]:
                return "captcha-unavailable"
        return "submitted"
    except Exception:
        return "submitted"


# --- one account, end to end (single login) ---


def _seed_for(uid):
    if uid.isdigit():
        return int(uid) % 1000000
    return sum(uid.encode()) % 1000000


def _existing_dp(dp_dir, uid):
    """Path of an already-generated valid image for this uid, else None.
    Reusing it saves free-pool quota on reruns."""
    for ext, magic in ((".png", PNG_MAGIC), (".jpg", JPEG_MAGIC)):
        path = os.path.join(dp_dir, uid + ext)
        try:
            with open(path, "rb") as f:
                head = f.read(len(magic))
            if head == magic:
                return path
        except Exception:
            continue
    return None


def _goto_profile(page, url, timeout=30000):
    """Load a profile page without ever raising. Facebook's 'load'
    event can hang on slow assets, so wait only for DOM content and
    retry once. Returns True if the page loaded, else False - the
    caller turns False into a per-account failure, never a crash."""
    for _ in range(2):
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return True
        except Exception:
            continue
    return False


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
        if not _goto_profile(page, FB_PROFILE_URL.format(uid=uid)):
            return {"uid": uid, "name": "", "ok": False,
                    "skipped": False, "via": "cookie",
                    "detail": "profile page did not load"}
        _human_pause(1.0, 2.0)
        via = "cookie"
        logged_in = _is_logged_in(page, ctx)
        if not logged_in:
            # Cookie dead (common for old IDs) -> password fallback.
            via = "password"
            status = password_login(page, uid, account["password"])
            if status == "checkpoint":
                return {"uid": uid, "name": "", "ok": False,
                        "skipped": False, "via": via,
                        "detail": "checkpoint - skipped, no retry"}
            if status == "captcha-unavailable":
                return {"uid": uid, "name": "", "ok": False,
                        "skipped": False, "via": via,
                        "detail": "captcha solver unavailable - "
                                  "solve in browser"}
            if not _goto_profile(page, FB_PROFILE_URL.format(uid=uid)):
                return {"uid": uid, "name": "", "ok": False,
                        "skipped": False, "via": via,
                        "detail": "profile page did not load"}
            _human_pause(1.0, 2.0)
            if not _is_logged_in(page, ctx):
                return {"uid": uid, "name": "", "ok": False,
                        "skipped": False, "via": via,
                        "detail": "login failed"}
        name = read_profile_name(page)
        # The header DP image is not a gate: on some loads it is
        # never rendered (no alt="Profile picture" img in the DOM)
        # while the actions trigger still exists. Retry once after a
        # reload; if it is still missing, proceed anyway - the
        # skip check below only runs when a picture is present, and
        # apply_dp_on_page verifies by toast or URL change.
        if not _wait_for_pic(page):
            if _goto_profile(page, FB_PROFILE_URL.format(uid=uid)):
                _human_pause(1.0, 2.0)
                _wait_for_pic(page)
        if has_custom_dp(page):
            return {"uid": uid, "name": name, "ok": True, "skipped": True,
                    "via": via, "detail": "already has DP - skipped"}
        existing = _existing_dp(dp_dir, uid)
        if existing:
            res = apply_dp_on_page(page, existing)
            res["uid"] = uid
            res["name"] = name
            res["via"] = via
            res["skipped"] = False
            if res["ok"]:
                res["detail"] = "applied from existing file"
            return res
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


# --- interactive entry (main.py mode 5) ---


def run_dp_mode():
    print(f"{CYAN}=== DP Apply (test version) ==={WHITE}")
    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if api_key:
        print(f"{CYAN}Pollinations key set - using keyed endpoint.{WHITE}")
    else:
        print(f"{YELLOW}No Pollinations key set - using anonymous "
              f"endpoint (shared pool, may hit limits). Set "
              f"POLLINATIONS_API_KEY for your own quota.{WHITE}")
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
            try:
                res = process_account(pw, account, api_key, dp_dir,
                                      headless=False)
            except Exception as e:
                # One account's unexpected failure must never kill
                # the batch: record it and move to the next account.
                res = {"uid": account["uid"], "name": "",
                       "ok": False, "skipped": False, "via": "",
                       "detail": f"unexpected error: {e}"}
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
                if "402" in res["detail"]:
                    print(f"{RED}[DP] Anonymous free pool exhausted - "
                          f"stopping the batch. Set a free Pollinations "
                          f"key or retry later; already-applied DPs are "
                          f"kept.{WHITE}")
                    break
    print(f"{CYAN}Done: applied {applied}, skipped {skipped}, "
          f"failed {failed}. DPs saved in {dp_dir}{WHITE}")
