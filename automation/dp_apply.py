"""DP Apply - profile pictures for IDs without a DP.

Run via the DP option in main.py Modes 2 and 3. Reads
output/browser_accounts.txt (the same file every mode writes/reads
through core.path_manager), opens each account, and applies a DP
picked from the dp_pics/ folder (male/ and female/, matched by
exact gender and name) only where the ID has none. IDs that
already have a DP are left as they are, never overwritten.

One account at a time, human behaviour throughout (shared helpers
from browser_register), a gap between accounts, one failure never
stops the batch, a checkpoint stops the account with no retry
(stand-down rule). Login is the same cookie login as reviews
(fb_login); a dead cookie falls back to password login.

No image generation lives here: pictures come from files only.
"""
import os
import time

from playwright.sync_api import sync_playwright

from automation.browser_register import (
    _human_click,
    _human_pause,
    _human_type,
)
from automation.dp_pick import (
    _norm,
    detect_gender,
    folder_status,
    pic_stems,
    pick_dp,
    record_used,
    used_file_path,
)
from automation.fb_automation import fb_login
from core.path_manager import get_output_dir
from ui.colors import GREEN, WHITE, CYAN

FB_PROFILE_URL = "https://www.facebook.com/profile.php?id={uid}"
FB_LOGIN_URL = "https://www.facebook.com/login"

# A custom photo is served from Facebook's user-content CDN. Default
# avatars come from the static CDN or carry one of these markers. Any
# unrecognised picture URL is treated as custom (safe side: missing
# one DP is harmless, overwriting an existing DP is not).
# Facebook's own default avatar is served from the user-content CDN
# too (scontent), so "scontent" alone does NOT prove a custom
# picture. The default avatar is a fixed stock photo, but the
# logged-in profile page serves a DIFFERENT object than the public
# graph endpoint: the graph endpoint returns
# 84628273_176159830277856_972693363922829312_n.jpg (id
# 176159830277856), while the profile page serves
# 453178253_471506465671661_2781666950760530985_n.png (seen live
# 2026-11-05 on an ID with no DP). Both ids are markers. Check
# these markers BEFORE the scontent shortcut, or the default avatar
# is misread as a custom DP.
DEFAULT_DP_MARKERS = ("silhouette", "static.xx", "empty-profile",
                      "default", "176159830277856",
                      "453178253_471506465671661_2781666950760530985")


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
    """True only for a real logged-in session. The discriminator is
    the Log in control: a logged-out page always shows one, a
    logged-in session never does. Cookie presence (c_user) is
    required as well. The profile name is NOT required here: the
    header renders asynchronously, and a slow name must never turn
    a good login into a failure."""
    if not has_c_user(ctx.cookies()):
        return False
    for role in ("link", "button"):
        try:
            if page.get_by_role(role, name="Log in").first.is_visible():
                return False
        except Exception:
            pass
    return True


# --- profile reading ---


# UI labels that are never a profile name.
_NAME_STOPLIST = {
    "notifications", "facebook", "home", "menu", "search", "watch",
    "marketplace", "groups", "gaming", "see more", "create", "log in",
    "sign up", "settings", "help", "profile", "friends", "photos",
    "videos", "about", "posts",
}


def _plausible_name(text, candidate_names=()):
    """A profile name looks like a person's name, not UI chrome.
    A text that matches a DP pic filename is always accepted."""
    text = (text or "").strip()
    if not text:
        return ""
    if _norm(text) in candidate_names:
        return text
    # A notification-count title ("(4) Facebook") is never a
    # person's name: reject any text starting with "(digits)".
    import re as _re
    if _re.match(r"^\(\d+\)", text):
        return ""
    low = text.lower()
    if low in _NAME_STOPLIST:
        return ""
    if "log in" in low or "sign up" in low:
        return ""
    if len(text.split()) < 2:
        return ""
    return text


def _try_read_profile_name(page, candidate_names):
    """One attempt at the profile name: every h1, og:title, then
    the page body matched against the DP pic filenames. The FIRST
    h1 is page chrome ("Notifications"), never the profile name,
    and the page title is just "Facebook" (with a "(2) " count) -
    neither is the name. The owner's name IS in the body text from
    ~3s after load (seen live 2026-11-05)."""
    try:
        for text in page.locator("h1").all_inner_texts(timeout=2000):
            name = _plausible_name(text, candidate_names)
            if name:
                return name
    except Exception:
        pass
    try:
        og = page.locator(
            'meta[property="og:title"]').first.get_attribute(
                "content", timeout=2000)
        name = _plausible_name(og, candidate_names)
        if name:
            return name
    except Exception:
        pass
    if candidate_names:
        try:
            body = page.evaluate(
                "() => (document.body ? document.body.innerText : '')"
                ".slice(0, 1000)")
            low_body = " " + _norm(body or "") + " "
            best = ""
            for stem in candidate_names:
                if stem and (" " + stem + " ") in low_body:
                    if len(stem) > len(best):
                        best = stem
            if best:
                import re as _re
                m = _re.search(_re.escape(best), body or "",
                               _re.IGNORECASE)
                return m.group(0) if m else best
        except Exception:
            pass
    return ""


def read_profile_name(page, candidate_names=(), timeout_s=10):
    """Profile name, polled until it appears. The header renders
    asynchronously: at 1s the h1 is empty and the name is not in
    the body text yet; from ~3s the name is on the page. Polls for
    up to timeout_s; "" if no name appears."""
    deadline = time.time() + timeout_s
    while True:
        name = _try_read_profile_name(page, candidate_names)
        if name:
            return name
        if time.time() >= deadline:
            return ""
        try:
            page.wait_for_timeout(1000)
        except Exception:
            pass


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
    try:
        page.locator("svg image").first.wait_for(
            state="attached", timeout=5000)
        return True
    except Exception:
        return False


def _pic_src(page):
    """URL of the current profile picture, or None. Tries the
    <img> candidates first, then the SVG image href (the
    header circle on current markup)."""
    loc = _pic_locator(page)
    if loc is not None:
        try:
            src = loc.get_attribute("src", timeout=5000)
            if src:
                return src
        except Exception:
            pass
    return _svg_pic_href(page)


def has_custom_dp(page):
    """True if the profile already has a custom picture, False if the
    picture is a default avatar (i.e. the ID has no DP yet)."""
    src = _pic_src(page)
    if not src:
        return False
    low = src.lower()
    if any(m in low for m in DEFAULT_DP_MARKERS):
        return False
    if "scontent" in low:
        return True
    return True  # unrecognised URL: treated as custom


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


def _svg_pic_href(page):
    """Href of the profile-picture SVG <image>. Facebook renders
    the header DP circle as an SVG image, not an <img>. The pic
    lives inside a [aria-label="Profile picture"] container; a
    bare "largest SVG on the page" is wrong because the cover
    photo (if an SVG) is larger. None if no usable href."""
    try:
        return page.evaluate("""() => {
            const inPic = (el) => {
                let p = el;
                while (p) {
                    const a = p.getAttribute && p.getAttribute('aria-label');
                    if (a === 'Profile picture') return true;
                    p = p.parentElement;
                }
                return false;
            };
            const imgs = [...document.querySelectorAll('svg image')]
                .map(e => ({href: e.getAttribute('href')
                            || e.getAttribute('xlink:href') || '',
                            w: e.getBoundingClientRect().width,
                            inPic: inPic(e)}))
                .filter(x => x.href && x.w > 0);
            if (!imgs.length) return null;
            const pic = imgs.find(x => x.inPic);
            if (pic) return pic.href;
            // No pic-container SVG: take a profile-pic-sized one
            // (32-400px). The cover/banner is far larger and
            // icons are far smaller.
            const sized = imgs.filter(x => x.w >= 32 && x.w <= 400);
            if (sized.length) {
                sized.sort((a, b) => b.w - a.w);
                return sized[0].href;
            }
            return null;
        }""")
    except Exception:
        return None


def _js_click_by_text(page, exact_text):
    """JS-click the element whose rendered text is exactly exact_text.
    Playwright role clicks time out on this dialog because the dialog
    overlay intercepts them; a JS click does not. Matches on innerText
    (rendered text), NOT textContent: Facebook obfuscates textContent
    with combining characters, so exact textContent matches fail on
    live pages. Prefers a role=menuitem/button match, else the last
    (deepest) match - nested ancestors share the rendered text of the
    clickable leaf. Returns True if an element was clicked, else
    False."""
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
    short pause is not enough. Returns True if found."""
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
    Returns dict(ok, detail). Live 2026-11-05: the edit control is
    aria-label "Profile picture actions"; clicking it OPENS the menu
    (confirmed live, menu items: "Choose profile picture",
    "Upload Photo", "Add Frame"). The probe that set the file on the
    first file input hit the cover-photo flow instead, so the file is
    attached to the fourth input when four are present. Success is
    proved only by the picture URL changing; a missing control is
    never reported as success."""
    before = _pic_src(page)
    if before is None:
        return {"ok": False, "detail": "profile picture element not found"}
    # Live control first: hover the picture, then click the actions
    # control. In the live view the menu did not surface on hover
    # alone, so the click is what opens it.
    try:
        loc = _pic_locator(page)
        if loc is not None:
            loc.hover(timeout=5000)
    except Exception:
        pass
    _human_pause(0.5, 1.5)
    opened = False
    actions_clicked = _js_click_profile_actions(page)
    if actions_clicked:
        _human_pause(0.3, 0.7)
        for menu_text in ("Choose profile picture", "Upload Photo",
                          "Update profile picture"):
            if _wait_for_text(page, menu_text, timeout_s=5):
                opened = _js_click_by_text(page, menu_text)
                if opened:
                    break
    if not opened:
        # Fallback: the older Edit/Update buttons.
        opened = _try_click(page, [
            page.get_by_role("button", name="Edit profile picture").first,
            page.get_by_role("button", name="Update profile picture").first,
        ])
        if not opened:
            if actions_clicked:
                return {"ok": False,
                        "detail": "profile picture menu did not open"}
            return {"ok": False, "detail": "profile picture actions not found"}
        _human_pause(0.3, 0.7)
        if not _try_click(page, [
            page.get_by_role("button", name="Upload photo").first,
            page.get_by_role("button", name="Update profile picture").first,
        ]):
            return {"ok": False, "detail": "upload control not found"}
    _human_pause(0.3, 0.7)
    # Attach the file. The page holds several file inputs; the
    # profile-picture input is the fourth when four are present.
    # Never use the first input blindly: index 0 can set a cover
    # draft instead of a profile picture.
    try:
        inputs = page.locator('input[type="file"]')
        # Fail fast (10s): if the inputs never appear the menu
        # did not open right, and a slow poll here is what
        # leaves one ID stuck for a minute.
        for _ in range(20):
            if inputs.count() >= 4:
                break
            time.sleep(0.5)
        if inputs.count() >= 4:
            inputs.nth(3).set_input_files(photo_path, timeout=15000)
        else:
            # Never use the first input: index 0 can set a cover
            # draft instead of a profile picture. If the fourth
            # input never appears, the menu did not open right;
            # fail fast so the retry re-opens it.
            return {"ok": False, "detail": "profile file input not found"}
    except Exception:
        try:
            with page.expect_file_chooser(timeout=10000) as fc:
                _try_click(page, [
                    page.get_by_role("button", name="Upload photo").first])
            fc.value.set_files(photo_path, timeout=15000)
        except Exception as e:
            return {"ok": False, "detail": f"file attach failed: {e}"}
    _human_pause(0.3, 0.7)
    # Save / confirm. The crop editor renders only after the photo
    # is processed, so the Save button may not exist yet when the
    # file attach returns: live 2026-11-05 the editor shows Save
    # from ~2s, but a single check at ~1s misses it and reports
    # "save button not found". Poll for up to 20s instead of
    # checking once. Prefer the JS Save click: the dialog overlay
    # intercepts role clicks, and the dialog can be rendered twice
    # in the DOM, so the last Save button is the live one.
    saved = False
    for _ in range(40):
        if _js_click_save(page):
            saved = True
            break
        time.sleep(0.5)
    if not saved:
        if not _try_click(page, [
            page.get_by_role("button", name="Save", exact=True).first,
            page.get_by_role("button", name="Crop and save").first,
            page.get_by_role("button", name="Done").first,
        ]):
            return {"ok": False, "detail": "save button not found"}
    # Verify: the picture URL must actually change. Check at
    # once, then poll fast (0.5s) so the moment the DP lands
    # the tool knows instantly instead of waiting a fixed time.
    for _ in range(30):
        after = _pic_src(page)
        if after and after != before:
            return {"ok": True, "detail": "profile picture changed"}
        time.sleep(0.5)
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
        page.wait_for_timeout(1500)
        if "checkpoint" in page.url.lower():
            return "checkpoint"
        return "submitted"
    except Exception:
        return "submitted"


# --- one account, end to end (single login) ---


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


def process_account(pw, account, headless=False):
    """Login -> read name -> leave it if DP exists -> else read gender,
    pick a pic from dp_pics/ (name + gender match) and apply it.
    Login uses the same cookie login as reviews (fb_login) and trusts
    it the same way; a dead cookie falls back to password login only
    when a password is in the file. Returns dict
    (uid, name, ok, has_dp, via, detail)."""
    uid = account["uid"]
    browser = pw.chromium.launch(headless=headless,
                                 args=["--no-sandbox"])
    try:
        ctx = browser.new_context()
        page = ctx.new_page()
        via = "cookie"
        logged_in = False
        if account.get("cookies"):
            try:
                logged_in = fb_login(ctx, page, account["cookies"])
            except Exception:
                logged_in = False
        if logged_in:
            # Cookie login succeeded - trust it exactly like reviews
            # does. No second login gate here: the old re-check
            # demanded the profile name in h1, and a slow header
            # threw away a good cookie login, then the empty-password
            # fallback could never work.
            if not _goto_profile(page, FB_PROFILE_URL.format(uid=uid)):
                return {"uid": uid, "name": "", "ok": False,
                        "has_dp": False, "via": via,
                        "detail": "profile page did not load"}
            _human_pause(0.3, 0.7)
            # Dead cookie: the session is gone (login wall or no
            # c_user). Fall through to the password login below
            # instead of skipping: if a password is in the file
            # the ID opens with uid+password and the tool moves on.
            if not _is_logged_in(page, ctx):
                logged_in = False
        if not logged_in:
            # Cookie login failed or the cookie is dead. Fall back
            # to uid+password and move on. Password fallback only
            # when a password is actually in the file - with none
            # (uid || cookie lines) a password attempt can never work.
            if not account.get("password"):
                return {"uid": uid, "name": "", "ok": False,
                        "has_dp": False, "via": via,
                        "detail": "login failed"}
            via = "password"
            status = password_login(page, uid, account["password"])
            if status == "checkpoint":
                return {"uid": uid, "name": "", "ok": False,
                        "has_dp": False, "via": via,
                        "detail": "checkpoint - stopped, no retry"}
            if not _goto_profile(page, FB_PROFILE_URL.format(uid=uid)):
                return {"uid": uid, "name": "", "ok": False,
                        "has_dp": False, "via": via,
                        "detail": "profile page did not load"}
            _human_pause(0.3, 0.7)
            if not _is_logged_in(page, ctx):
                return {"uid": uid, "name": "", "ok": False,
                        "has_dp": False, "via": via,
                        "detail": "login failed"}
        try:
            candidates = pic_stems()
        except Exception:
            candidates = []
        name = read_profile_name(page, candidates)
        if not _wait_for_pic(page):
            return {"uid": uid, "name": name, "ok": False,
                    "has_dp": False, "via": via,
                    "detail": "profile picture element not found"}
        if has_custom_dp(page):
            return {"uid": uid, "name": name, "ok": True, "has_dp": True,
                    "via": via, "detail": "already has DP"}
        gender, method = detect_gender(page, uid, name)
        # Gender read moves the page to About - go back to the
        # profile before the upload (apply_dp_on_page needs the
        # profile page).
        if not _goto_profile(page, FB_PROFILE_URL.format(uid=uid)):
            return {"uid": uid, "name": "", "ok": False,
                    "has_dp": False, "via": via,
                    "detail": "profile page did not load"}
        _human_pause(0.3, 0.7)
        picked = pick_dp(name, gender)
        if not picked:
            if gender:
                detail = (f"no DP pic for {gender} - add photos to "
                          f"dp_pics/{gender}/")
            else:
                detail = (f"gender unknown and no pic named for "
                          f"'{name}' - add a pic named '{name}' to "
                          "dp_pics/male/ or dp_pics/female/")
            return {"uid": uid, "name": name, "ok": False,
                    "has_dp": False, "via": via, "detail": detail}
        # Retry in the same session (same page, no re-login and
        # no re-open of the ID): a transient menu, attach, save
        # or verify failure can succeed on the next attempt.
        # If a previous attempt actually applied the DP but the
        # verify missed it, the pic is already custom, so treat
        # it as applied instead of uploading again.
        res = {"ok": False, "detail": "not attempted"}
        for _attempt in range(2):
            if _attempt > 0 and has_custom_dp(page):
                res = {"ok": True,
                       "detail": "profile picture changed"}
                break
            res = apply_dp_on_page(page, picked["path"])
            if res["ok"]:
                break
        if res["ok"]:
            record_used(used_file_path(), picked["path"])
            res["detail"] = ("profile picture changed "
                             f"({os.path.basename(picked['path'])}, "
                             f"{picked['gender'] or 'gender unknown'}, "
                             f"{picked['reason']}, gender via {method})")
            # Hold the profile open 2s so the user can see the
            # new DP before the browser closes and we move on.
            # Fast: 2s, not 5s — the work must be quick.
            time.sleep(2)
        res["uid"] = uid
        res["name"] = name
        res["via"] = via
        res["has_dp"] = False
        return res
    finally:
        browser.close()


# --- interactive entry (main.py Modes 2 and 3) ---


def run_dp_mode():
    print(f"{CYAN}DP Apply{WHITE}")
    status = folder_status()
    print(f"{CYAN}Male: {status['male']}{WHITE}")
    print(f"{CYAN}Female: {status['female']}{WHITE}")
    accounts = parse_accounts_file(
        os.path.join(get_output_dir(), "browser_accounts.txt"))
    n = len(accounts)
    print(f"{CYAN}Found {n} account{'s' if n != 1 else ''}{WHITE}")
    if status["male"] + status["female"] == 0 or not accounts:
        return
    with sync_playwright() as pw:
        for i, account in enumerate(accounts):
            try:
                res = process_account(pw, account, headless=False)
            except Exception as e:
                # One account's unexpected failure must never kill
                # the batch: record it and move to the next account.
                res = {"uid": account["uid"], "name": "",
                       "ok": False, "has_dp": False, "via": "",
                       "detail": f"unexpected error: {e}"}
            label = res.get("name") or res["uid"]
            if res.get("ok") and not res.get("has_dp"):
                print(f"{GREEN}[DP] {label}: done{WHITE}")
            elif res.get("has_dp"):
                print(f"{CYAN}[DP] {label}: already has DP, skipped{WHITE}")
            else:
                print(f"{WHITE}[DP] {label}: failed - "
                      f"{res.get('detail', '')}{WHITE}")
