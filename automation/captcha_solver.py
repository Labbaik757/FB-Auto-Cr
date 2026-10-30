"""Self solver for Facebook's two_step reCAPTCHA gate (TEST VERSION).

Used ONLY for old IDs in Mode 5 (cookie extract) and old-ID DP
(dp_apply password fallback). New IDs do NOT get this gate, so this
module is never wired into Mode 2 creation.

Gate (live-verified 2026-10-29, Sophia Wilson audit):
  facebook.com/two_step_verification/authentication/ renders an
  EMPTY body; the gate lives in iframes:
    fbsbx.com/captcha/recaptcha/iframe/
      -> google.com/recaptcha/enterprise/anchor  (#recaptcha-anchor)
      -> google.com/recaptcha/enterprise/bframe  (td.rc-imageselect-tile,
         Verify or NEXT button)
  Puzzle grid: 3x3 VISIBLE tiles, but the DOM holds more (replacement
  tiles). Click ONLY visible tiles, mapped by visible position 0-8,
  never by raw DOM index. After clicking, tiles may be replaced and
  a second puzzle may follow - loop until the URL leaves two_step.

Solving: each visible tile is screenshotted and classified with
Gemini vision (gemini-2.0-flash, same model/key source as
fb_automation.py: GEMINI_API_KEY env, else gemini_api_key.txt in
the base storage dir). No puzzle answer or tile index is ever
hard-coded; every tile is classified on every run.

If the Gemini key is missing or the API errors, solve_recaptcha()
returns ok=False detail="no-gemini-key" and NEVER claims a solve.
The caller must then STOP for the user to solve it in the visible
browser (same pattern as the OTP stop point) and keep polling
c_user+xs so a manual solve is detected. Never record any password,
key, or cookie value.
"""

import os
import re
import time

MAX_PUZZLES = 5
MODEL_NAME = "gemini-2.0-flash"


def get_gemini_key():
    """GEMINI_API_KEY env first, else gemini_api_key.txt in the base
    storage dir (same source as fb_automation.py). Returns "" if none."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        from core.path_manager import get_base_storage_dir
        path = os.path.join(get_base_storage_dir(), "gemini_api_key.txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def _load_model():
    """Gemini vision model, or None if no key / library missing."""
    if not get_gemini_key():
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=get_gemini_key())
        return genai.GenerativeModel(MODEL_NAME)
    except Exception:
        return None


def _frames(page):
    try:
        frames = page.frames
        return list(frames) if frames else []
    except Exception:
        return []


def _frame_with(page, needle):
    for fr in _frames(page):
        try:
            if needle in (fr.url or "").lower():
                return fr
        except Exception:
            continue
    return None


def _iframe_present(page):
    """True if an fbsbx/recaptcha iframe is on the page. Frame URLs
    only - never body text."""
    for fr in _frames(page):
        try:
            url = (fr.url or "").lower()
            if "fbsbx" in url or "recaptcha" in url:
                return True
        except Exception:
            continue
    for sel in ('iframe[src*="fbsbx"]', 'iframe[src*="recaptcha"]'):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def detect_gate(page):
    """Return "recaptcha" | "otp" | "checkpoint" | "none".
    Detection is by URL / frame / OTP field only - never body text."""
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if "two_step" in url or _iframe_present(page):
        return "recaptcha"
    try:
        if page.locator('input[name="approvals_code"]').count() > 0:
            return "otp"
    except Exception:
        pass
    if "checkpoint" in url:
        return "checkpoint"
    return "none"


def _has_c_user(cookies):
    return any(c.get("name") == "c_user" and c.get("value")
               for c in (cookies or []))


def _has_xs(cookies):
    return any(c.get("name") == "xs" and c.get("value")
               for c in (cookies or []))


def _get_cookies(page, ctx):
    if ctx is not None:
        try:
            return ctx.cookies()
        except Exception:
            return []
    try:
        return page.context.cookies()
    except Exception:
        return []


def _is_solved(page, ctx):
    """Solved only when the URL has left two_step AND (when a
    context is available) both c_user and xs are present."""
    try:
        if "two_step" in (page.url or "").lower():
            return False
    except Exception:
        return False
    cookies = _get_cookies(page, ctx)
    if not cookies:
        # No context to check (e.g. dp_apply password_login, which
        # only has the page): URL leaving two_step is the signal;
        # the caller re-verifies the session via its own login check.
        return True
    return _has_c_user(cookies) and _has_xs(cookies)


def _read_target(bframe):
    """Challenge target text, e.g. 'bicycles' from
    'Select all images with bicycles'. Returns "" if unreadable."""
    text = ""
    for sel in (".rc-imageselect-desc",
                "div.rc-imageselect-desc-wrapper",
                ".rc-imageselect-challenge"):
        try:
            loc = bframe.locator(sel).first
            text = loc.inner_text(timeout=5000).strip()
            if text:
                break
        except Exception:
            continue
    if not text:
        return ""
    m = re.search(r"with\s+([a-zA-Z][a-zA-Z ]*?)(?:\s+If\b|\.|$)",
                  text, re.I)
    if m:
        return m.group(1).strip().lower()
    return text.strip().lower()


def _visible_tiles(bframe):
    """ONLY visible td.rc-imageselect-tile, in visible position
    order 0-8. Hidden DOM tiles (replacements not yet shown) are
    ignored - clicking them is the classic failure mode."""
    out = []
    try:
        tiles = bframe.locator("td.rc-imageselect-tile")
        count = tiles.count()
    except Exception:
        return out
    for i in range(count):
        if len(out) >= 9:
            break
        try:
            tile = tiles.nth(i)
            if tile.is_visible():
                out.append(tile)
        except Exception:
            continue
    return out


def _classify_with_gemini(model, target, png_bytes):
    """Ask Gemini vision: does this tile contain <target>?
    Answer only YES or NO. Any API error raises - the caller turns
    it into a no-key failure, never a fake solve."""
    prompt = (f"Does this image tile contain {target}? "
              "Answer only YES or NO.")
    resp = model.generate_content([
        prompt,
        {"mime_type": "image/png", "data": png_bytes},
    ])
    text = (resp.text or "").strip().upper()
    return text.startswith("YES")


def _click_verify(bframe):
    """Click Verify, else NEXT, else the verify button id.
    Returns True if a click was attempted, else False."""
    candidates = []
    for name in ("Verify", "NEXT"):
        try:
            candidates.append(
                bframe.get_by_role("button", name=name).first)
        except Exception:
            pass
    for sel in ("#recaptcha-verify-button",
                'button:has-text("Verify")',
                'button:has-text("NEXT")'):
        try:
            candidates.append(bframe.locator(sel).first)
        except Exception:
            pass
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def _wait_for_bframe(page, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        fr = _frame_with(page, "bframe")
        if fr is not None:
            return fr
        time.sleep(1)
    return None


def solve_recaptcha(page, ctx=None, classify=None, model=None,
                    max_puzzles=MAX_PUZZLES):
    """Solve the two_step reCAPTCHA gate on the given page.
    Returns {"ok": True, "detail": ...} on success, else
    {"ok": False, "detail": "no-gemini-key"} when the key is
    missing or the Gemini API errors, or another detail string
    describing the failure. Never claims success without the
    URL leaving two_step (and c_user+xs, when a context is given).
    classify: optional stub (target, png_bytes) -> bool, for tests.
    model: optional pre-built Gemini model, for tests."""
    if classify is None:
        if model is None:
            model = _load_model()
        if model is None:
            return {"ok": False, "detail": "no-gemini-key"}

        def classify(target, png_bytes, _m=model):
            return _classify_with_gemini(_m, target, png_bytes)

    try:
        # 1. Click the "I'm not a robot" anchor.
        anchor = _frame_with(page, "anchor")
        if anchor is not None:
            try:
                anchor.locator("#recaptcha-anchor").click(timeout=10000)
            except Exception:
                pass
        time.sleep(2)
        if _is_solved(page, ctx):
            return {"ok": True, "detail": "anchor passed, no puzzle"}

        # 2. Loop over puzzles (replacements / second puzzle).
        for puzzle_no in range(1, max_puzzles + 1):
            if _is_solved(page, ctx):
                return {"ok": True, "detail": "solved"}
            bframe = _wait_for_bframe(page)
            if bframe is None:
                if _is_solved(page, ctx):
                    return {"ok": True, "detail": "solved"}
                return {"ok": False,
                        "detail": "recaptcha frame not found"}
            target = _read_target(bframe)
            if not target:
                return {"ok": False,
                        "detail": "challenge text not found"}
            tiles = _visible_tiles(bframe)
            if not tiles:
                return {"ok": False, "detail": "no visible tiles"}
            for tile in tiles:
                try:
                    png = tile.screenshot()
                except Exception:
                    continue
                try:
                    is_target = classify(target, png)
                except Exception:
                    return {"ok": False, "detail": "no-gemini-key"}
                if is_target:
                    try:
                        tile.click(timeout=5000)
                    except Exception:
                        pass
                    time.sleep(0.3)
            # Let replacement tiles settle before verifying.
            time.sleep(1.5)
            if not _click_verify(bframe):
                return {"ok": False,
                        "detail": "verify button not found"}
            time.sleep(2)
            if _is_solved(page, ctx):
                return {"ok": True,
                        "detail": f"solved after {puzzle_no} puzzle(s)"}
        if _is_solved(page, ctx):
            return {"ok": True, "detail": "solved"}
        return {"ok": False,
                "detail": "recaptcha not solved after "
                          f"{max_puzzles} puzzles"}
    except Exception as e:
        return {"ok": False, "detail": f"solver error: {e}"}
