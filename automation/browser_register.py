"""
Browser-based Facebook account registration using Playwright.

This module is STANDALONE - it does not modify or depend on the HTTP-based
create_task.py. It automates the Facebook signup form in a real browser
with human-like behavior (slow typing, random pauses).

Usage (standalone test):
    python -m automation.browser_register

Integration:
    Called from main.py when user selects "Browser" mode.
"""

import random
import time
import sys
import os
import threading

def _input_with_timeout(prompt, timeout=10):
    """Get input with timeout. Returns None on timeout."""
    result = [None]
    def _get():
        try:
            result[0] = input(prompt)
        except Exception:
            pass
    t = threading.Thread(target=_get, daemon=True)
    t.start()
    t.join(timeout)
    return result[0]

# Add project root to path for standalone execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faker import Faker

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, LINE
from ui.display import print_lock
from core.counter import Counter


def _human_pause(min_s=1.0, max_s=3.0):
    """Fixed 1 second pause per user."""
    time.sleep(1.0)


def _human_mouse_move(page, x, y, steps=15):
    """Move mouse in a human-like curve with slight randomness."""
    import random as _r
    for i in range(1, steps + 1):
        t = i / steps
        nx = x * t + _r.uniform(-8, 8) * (1 - t)
        ny = y * t + _r.uniform(-8, 8) * (1 - t) + 80 * t * (1 - t)
        try:
            page.mouse.move(nx, ny, steps=1)
        except Exception:
            break
        time.sleep(_r.uniform(0.01, 0.03))

def _human_click(page, locator):
    """Hover with human mouse movement, then click."""
    try:
        box = locator.bounding_box(timeout=5000)
        if box:
            _human_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            time.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass
    locator.click()


def _human_type(page, selector, text, min_delay=80, max_delay=250):
    """
    Type text character by character with random delays,
    like a human typing. Accepts CSS selector string or Locator.
    """
    element = selector if hasattr(selector, "click") else page.locator(selector)
    element.click()
    _human_pause(0.3, 0.8)
    # 15% chance: make a typo then correct it (human-like)
    _typo_done = False
    for idx, char in enumerate(text):
        element.press_sequentially(char, delay=random.randint(min_delay, max_delay))
        if not _typo_done and len(text) > 4 and idx == len(text) // 2 and random.random() < 0.15:
            _typo_done = True
            _wrong = random.choice("asdfghjkl")
            element.press_sequentially(_wrong, delay=random.randint(80, 150))
            time.sleep(random.uniform(0.3, 0.7))
            element.press("Backspace")
            time.sleep(random.uniform(0.2, 0.5))
    _human_pause(0.5, 1.5)


def _select_birthday(page, day, month, year):
    """Select birthday via custom comboboxes (click combobox, then option)."""
    ok = True
    for combo_name, opt_name, use_exact in [
        ("Select Month", month, False),
        ("Select Day", str(day), True),
        ("Select Year", str(year), True),
    ]:
        try:
            page.get_by_role("combobox", name=combo_name).click()
            _human_pause(0.5, 1.0)
            page.get_by_role("option", name=opt_name, exact=use_exact).click()
            _human_pause(0.3, 0.6)
            page.keyboard.press("Escape")  # Close listbox to commit value
            _human_pause(0.3, 0.6)
            with print_lock:
                print(f"{GREEN}[Browser] Birthday {combo_name} -> {opt_name}{WHITE}")
            _human_pause(0.5, 1.0)
        except Exception as e:
            with print_lock:
                print(f"{RED}[Browser] Birthday {combo_name} FAILED: {e}{WHITE}")
            ok = False
    return ok


def _select_gender(page, gender):
    """Select gender via combobox (options: Female/Male/Custom)."""
    opt = "Female" if gender.lower() == "female" else "Male"
    ok = False
    try:
        # Try exact name first, then 4th combobox (after 3 birthday ones)
        try:
            combo = page.get_by_role("combobox", name="Select your gender")
            combo.wait_for(timeout=5000)
        except Exception:
            with print_lock:
                print(f"{YELLOW}[Browser] Gender by name not found, trying 4th combobox{WHITE}")
            combo = page.get_by_role("combobox").nth(3)
            combo.wait_for(timeout=5000)
        combo.click()
        _human_pause(0.5, 1.0)
        option = page.get_by_role("option", name=opt, exact=True)
        option.wait_for(state="visible", timeout=10000)
        option.click()
        _human_pause(0.3, 0.6)
        page.keyboard.press("Escape")  # Close listbox to commit value
        _human_pause(0.3, 0.6)
        # Verify selection
        combo_text = combo.inner_text()
        if opt.lower() in combo_text.lower():
            with print_lock:
                print(f"{GREEN}[Browser] Gender -> {opt} (verified){WHITE}")
            ok = True
        else:
            with print_lock:
                print(f"{YELLOW}[Browser] Gender click done but not verified: {combo_text}{WHITE}")
            ok = True  # Click succeeded, assume ok
    except Exception as e:
        with print_lock:
            print(f"{RED}[Browser] Gender FAILED: {e}{WHITE}")
    _human_pause(0.5, 1.0)
    return ok


def _parse_number_entry(entry):
    """Parse 'number,url' or 'number|url' format. Returns (number, otp_url or None)."""
    entry = entry.strip()
    if entry.startswith("#") or not entry:
        return None, None
    for sep in [",", "|"]:
        if sep in entry:
            parts = entry.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return entry, None


def _apply_fingerprint_spoof(context):
    """Inject canvas/WebGL fingerprint spoofing. Each account gets a different fingerprint."""
    import random as _rand
    # Random GPU from common list (per-account)
    _gpus = [
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ]
    _vendor, _renderer = _rand.choice(_gpus)
    _noise = _rand.randint(1, 10)

    _js = f"""
    (function() {{
        const _noiseSeed = {_noise};
        // --- Canvas spoof: subtle noise on toDataURL ---
        const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(...args) {{
            try {{
                const ctx = this.getContext('2d');
                if (ctx) {{
                    const w = this.width, h = this.height;
                    if (w > 0 && h > 0) {{
                        const img = ctx.getImageData(0, 0, w, h);
                        const d = img.data;
                        for (let i = 0; i < d.length; i += 4) {{
                            d[i] = (d[i] + _noiseSeed) % 256;
                        }}
                        ctx.putImageData(img, 0, 0);
                    }}
                }}
            }} catch (e) {{}}
            return _origToDataURL.apply(this, args);
        }};
        // --- WebGL spoof: fake GPU vendor/renderer ---
        const _vendor = "{_vendor}";
        const _renderer = "{_renderer}";
        const _origGetParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return _vendor;
            if (param === 37446) return _renderer;
            return _origGetParam.apply(this, arguments);
        }};
        const _origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return _vendor;
            if (param === 37446) return _renderer;
            return _origGetParam2.apply(this, arguments);
        }};
        // --- Navigator spoof ---
        try {{
            Object.defineProperty(navigator, 'webdriver', {{ get: function() {{ return false; }} }});
            Object.defineProperty(navigator, 'plugins', {{ get: function() {{ return [1, 2, 3, 4]; }} }});
        }} catch (e) {{}}
        // --- AudioContext noise ---
        try {{
            var _origGCD = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function(ch) {{
                var data = _origGCD.apply(this, arguments);
                for (var i = 0; i < data.length; i += 97) {{
                    data[i] += (Math.random() - 0.5) * 0.0005;
                }}
                return data;
            }};
        }} catch (e) {{}}
    }})();
    """
    try:
        context.add_init_script(_js)
    except Exception:
        pass


def _click_resend_twice(page):
    """Click resend code button 3 times back-to-back (triggers OTP delivery)."""
    # First: click the expander below Continue to reveal resend option
    expander_selectors = [
        'button:has-text("Didn\'t get the code")',
        'a:has-text("Didn\'t get the code")',
        '[role="button"]:has-text("Didn\'t get the code")',
        'button:has-text("Need another way")',
        'a:has-text("Need another way")',
        'button:has-text("Try another way")',
        'a:has-text("Try another way")',
        'button:has-text("More options")',
    ]
    for sel in expander_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=500):
                btn.click()
                with print_lock:
                    print(f"{CYAN}[Browser] Expander clicked to reveal resend{WHITE}")
                _human_pause(1.0, 2.0)
                break
        except Exception:
            continue

    resend_selectors = [
        'button:has-text("Resend")',
        'a:has-text("Resend")',
        '[role="button"]:has-text("Resend")',
        'button:has-text("Send code again")',
        'a:has-text("Send again")',
        '[role="button"]:has-text("Send again")',
        'button:has-text("Resend SMS")',
        'a:has-text("Resend SMS")',
        'button:has-text("Resend code")',
        'a:has-text("Resend code")',
    ]
    clicked = 0
    for attempt in range(3):
        for sel in resend_selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=500):
                    btn.click()
                    clicked += 1
                    with print_lock:
                        print(f"{CYAN}[Browser] Resend clicked ({clicked}/3){WHITE}")
                    time.sleep(1.5)  # Human pause between resends
                    break
            except Exception:
                continue
        if clicked >= 3:
            break
    return clicked


def _fetch_otp_from_url(page, sms_url, timeout=20, interval=1):
    """
    Fetch OTP via HTTP requests (simple API endpoint).
    Response is plain text; 'no' prefix means no OTP yet.
    Returns the code or None.
    """
    import re
    import requests

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(sms_url, timeout=15)
            text = r.text.strip()
            if text and not text.startswith("no"):
                m = re.search(r"\d{4,8}", text)
                if m:
                    return m.group(0)
        except Exception:
            pass
        time.sleep(interval)
    return None


def browser_create_account(page, phone_number, password, counter=None, sms_url=None):
    """
    Create a single Facebook account in the browser.

    Args:
        page: Playwright page object (fresh context)
        phone_number: Phone number for registration
        password: Password to use
        counter: Optional Counter for stats

    Returns:
        dict with 'status' ('success'/'failed'/'error') and details
    """
    fake = Faker()

    # Blocked popular/generic names (never use these)
    BLOCKED_NAMES = {"king", "queen", "love", "kingdom", "prince", "princess",
                     "angel", "devil", "baby", "sweet", "cute", "hot", "sexy",
                     "star", "moon", "sun", "dark", "light", "dragon", "tiger",
                     "lion", "wolf", "boss", "admin", "test", "demo", "user",
                     "facebook", "fb", "meta", "official", "real", "fake"}

    # Name-based gender lists (per user reference)
    MALE_NAMES = {
        "james", "john", "robert", "michael", "william", "david",
        "joseph", "daniel", "matthew", "andrew", "ryan", "alexander",
        "chris", "kevin", "jason", "brian", "steve", "mark", "paul",
        "george", "henry", "jack", "oliver", "leo", "sam", "ben",
        "thomas", "liam", "noah", "ethan", "jacob", "lucas", "mason"
    }
    FEMALE_NAMES = {
        "mary", "emma", "sophia", "olivia", "isabella", "mia",
        "ava", "lily", "emily", "sarah", "jessica", "anna",
        "lisa", "kate", "jennifer", "rachel", "laura", "julia",
        "hannah", "amelia", "chloe", "grace", "ella", "ruby",
        "zoe", "lucy", "eva", "nora", "ivy", "aria", "sofia"
    }

    def gender_from_name(first_name: str) -> str:
        name = first_name.strip().lower()
        if name in MALE_NAMES:
            return "Male"
        if name in FEMALE_NAMES:
            return "Female"
        return "Male"  # default

    # Generate identity (skip blocked names)
    for _ in range(20):
        first_name = fake.first_name()
        last_name = fake.last_name()
        if first_name.lower() not in BLOCKED_NAMES and last_name.lower() not in BLOCKED_NAMES:
            break
    gender = gender_from_name(first_name)

    # Birthday: 18-40 years old (matches HTTP version)
    birth_date = fake.date_of_birth(minimum_age=18, maximum_age=40)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    birth_month = months[birth_date.month - 1]

    try:
        with print_lock:
            print(f"\n{CYAN}[Browser] Creating account for {phone_number}...{WHITE}")

        # Navigate to Facebook registration
        page.goto("https://www.facebook.com/r.php", wait_until="domcontentloaded")
        _human_pause(2.0, 4.0)
        # Human-like: scroll down and up as if reading the form
        try:
            page.evaluate("() => window.scrollTo(0, 300)")
            time.sleep(random.uniform(0.5, 1.0))
            page.evaluate("() => window.scrollTo(0, 0)")
            time.sleep(random.uniform(0.3, 0.7))
        except Exception:
            pass

        # Debug: check what page actually loaded
        with print_lock:
            print(f"{CYAN}[Browser] Page URL: {page.url}{WHITE}")
            print(f"{CYAN}[Browser] Page title: {page.title()}{WHITE}")

        # Wait for form to load (positional check)
        try:
            page.wait_for_selector('input[type="text"]', timeout=15000)
            n_text = page.locator('input[type="text"]').count()
            n_pwd = page.locator('input[type="password"]').count()
            with print_lock:
                print(f"{GREEN}[Browser] Form loaded: {n_text} text, {n_pwd} password{WHITE}")
            if n_text < 3 or n_pwd < 1:
                raise Exception("not enough fields")
        except Exception:
            page.screenshot(path="fb_reg_debug.png")
            with print_lock:
                print(f"{RED}[Browser] Signup form not loaded{WHITE}")
            counter.update("failed")
            return {"status": "failed", "number": phone_number, "reason": "form not loaded"}

        # Fill by position (was working): 3 text inputs + 1 password
        # Random order (human doesn't always go top-to-bottom)
        text_inputs = page.locator('input[type="text"]')
        pwd_inputs = page.locator('input[type="password"]')
        _fields = [(text_inputs.nth(0), first_name), (text_inputs.nth(1), last_name),
                   (text_inputs.nth(2), phone_number), (pwd_inputs.nth(0), password)]
        random.shuffle(_fields)
        for _loc, _val in _fields:
            _human_type(page, _loc, _val)

        # Select birthday
        dob_ok = _select_birthday(page, birth_date.day, birth_month, birth_date.year)

        # Select gender
        gender_ok = _select_gender(page, gender)

        _human_pause(1.0, 2.0)

        if not dob_ok or not gender_ok:
            with print_lock:
                print(f"{RED}[Browser] DOB or gender failed, not submitting{WHITE}")
            page.screenshot(path="fb_form_debug.png")
            counter.update("failed")
            return {"status": "failed", "number": phone_number, "reason": "dob/gender failed"}

        # Diagnostic: check field values before submit
        try:
            vals = page.evaluate("""() => {
                const texts = Array.from(document.querySelectorAll('input[type="text"]')).map(i => i.value);
                const pwd = document.querySelector('input[type="password"]');
                return {texts: texts, pwdLen: pwd ? pwd.value.length : 0};
            }""")
            with print_lock:
                print(f"{CYAN}[Browser] Field values: {vals['texts']} pwd_len={vals['pwdLen']}{WHITE}")
        except Exception:
            pass

        # Submit - try multiple selectors
        with print_lock:
            print(f"{YELLOW}[Browser] Submitting form...{WHITE}")
        submitted = False
        try:
            btn = page.get_by_role("button", name="Submit", exact=True)
            btn.wait_for(state="visible", timeout=10000)
            btn.scroll_into_view_if_needed(timeout=5000)
            _human_pause(0.5, 1.0)
            try:
                btn.click(timeout=10000)
            except Exception:
                with print_lock:
                    print(f"{YELLOW}[Browser] Normal click failed, trying JS click{WHITE}")
                btn.evaluate("el => el.click()")
            # Wait for navigation after submit
            navigated = False
            try:
                page.wait_for_url(lambda url: "/r.php" not in url and "/reg" not in url, timeout=10000)
                navigated = True
            except Exception:
                pass
            if not navigated:
                # Fallback: press Enter on password field
                with print_lock:
                    print(f"{YELLOW}[Browser] Click didn't navigate, trying Enter key{WHITE}")
                try:
                    pwd_inputs.nth(0).click()
                    _human_pause(0.3, 0.6)
                    page.keyboard.press("Enter")
                    page.wait_for_url(lambda url: "/r.php" not in url and "/reg" not in url, timeout=10000)
                    navigated = True
                except Exception:
                    pass
            # Final networkidle wait
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            submitted = True
            with print_lock:
                print(f"{GREEN}[Browser] Submit done (navigated: {navigated}){WHITE}")
            time.sleep(5.0)  # Human waits for OTP page to load
        except Exception as e:
            with print_lock:
                print(f"{RED}[Browser] Submit FAILED: {e}{WHITE}")
        if not submitted:
            # Dump all buttons/links for debugging
            buttons = page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"], a'));
                return els.map(e => ({
                    tag: e.tagName,
                    type: e.type || '',
                    name: e.name || '',
                    text: (e.innerText || e.value || '').slice(0, 40),
                    role: e.getAttribute('role') || ''
                })).filter(e => e.text.length > 0 || e.type === 'submit');
            }""")
            with print_lock:
                print(f"{RED}[Browser] Submit button not found. All clickable:{WHITE}")
                for b in buttons[:20]:
                    print(f"  tag={b['tag']} type={b['type']} name={b['name']} text={b['text']} role={b['role']}")
            counter.update("failed")
            return {"status": "failed", "number": phone_number, "reason": "submit not found"}

        # Wait for result - either success (logged in) or OTP/code page
        _human_pause(3.0, 5.0)

        # Verify we actually left the reg page (navigation = good sign)
        try:
            current_url = page.url
            with print_lock:
                print(f"{CYAN}[Browser] After submit URL: {current_url}{WHITE}")
        except Exception:
            # Page is navigating, wait for it to settle
            _human_pause(3.0, 5.0)
            try:
                current_url = page.url
            except Exception:
                current_url = ""
            with print_lock:
                print(f"{CYAN}[Browser] After navigation URL: {current_url}{WHITE}")

        try:
            if ("/reg" in current_url or "/r.php" in current_url) and "checkpoint" not in current_url:
                try:
                    page.screenshot(path="fb_submit_debug.png")
                    errors = page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('[role="alert"]'))
                            .map(e => e.innerText).filter(t => t.length > 0).slice(0, 5);
                    }""")
                except Exception:
                    errors = ["page navigating"]
                with print_lock:
                    print(f"{RED}[Browser] Still on reg page. Errors: {errors}{WHITE}")
                # Check aria-invalid on all inputs
                try:
                    invalids = page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('input')).map(i => ({
                            label: i.getAttribute('aria-label') || i.type,
                            invalid: i.getAttribute('aria-invalid'),
                            value: i.value.slice(0, 20)
                        })).filter(x => x.invalid === 'true');
                    }""")
                    with print_lock:
                        print(f"{RED}[Browser] Invalid fields: {invalids}{WHITE}")
                except Exception:
                    pass
                counter.update("failed")
                return {"status": "failed", "number": phone_number, "reason": f"submit failed: {errors}"}
        except Exception as e:
            with print_lock:
                print(f"{YELLOW}[Browser] URL check skipped (navigating): {e}{WHITE}")

        # Check if we're on confirmation page FIRST (even with cookie, OTP needed)
        try:
            current_url = page.url.lower()
        except Exception:
            current_url = ""
        on_confirm_page = "confirmemail" in current_url or "checkpoint" in current_url or "confirm" in current_url

        # Check if we're logged in (c_user cookie) AND not on confirm page
        cookies = page.context.cookies()
        c_user = next((c["value"] for c in cookies if c["name"] == "c_user"), None)

        if c_user and not on_confirm_page:
            # Success - save account
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            result = f"{c_user}|{password}|{cookie_str}"

            with print_lock:
                print(f"{GREEN}[Browser] SUCCESS: {c_user}{WHITE}")

            if counter:
                counter.update("success")

            return {
                "status": "success",
                "uid": c_user,
                "password": password,
                "cookies": cookie_str,
                "result_line": result,
            }

        # Check if OTP/code page appeared (or we're on confirm page)
        page_content = page.content().lower()
        if on_confirm_page or "code" in page_content or "confirm" in page_content or "otp" in page_content:
            code = None

            # Wait for OTP page to fully load, then click resend 3x to trigger OTP
            _human_pause(2.0, 3.0)
            resend_count = _click_resend_twice(page)
            if resend_count == 0:
                with print_lock:
                    print(f"{YELLOW}[Browser] Resend button not found, trying OTP fetch anyway{WHITE}")

            # Auto-fetch OTP from SMS URL if provided
            if sms_url:
                with print_lock:
                    print(f"{CYAN}[Browser] Auto-fetching OTP from SMS link...{WHITE}")
                code = _fetch_otp_from_url(page, sms_url)
                if code:
                    with print_lock:
                        print(f"{GREEN}[Browser] OTP received: {code}{WHITE}")
                else:
                    with print_lock:
                        print(f"{YELLOW}[Browser] Auto-fetch failed, manual input needed.{WHITE}")

            # Auto-fetch failed -> 10s manual entry window, then skip
            if not code:
                with print_lock:
                    print(f"{YELLOW}[Browser] OTP not received. Enter manually within 10s (or wait to skip):{WHITE}")
                manual = _input_with_timeout(f"{CYAN}Code (10s): {WHITE}", timeout=10)
                if manual and manual.strip() and manual.strip().lower() != "skip":
                    code = manual.strip()
                    with print_lock:
                        print(f"{GREEN}[Browser] Manual OTP: {code}{WHITE}")
                else:
                    with print_lock:
                        print(f"{YELLOW}[Browser] No OTP, skipping to next account.{WHITE}")
                    if counter:
                        counter.update("failed")
                    return {"status": "failed", "number": phone_number, "reason": "otp_not_received"}

            if code.lower() != "skip" and code:
                # Fill OTP and confirm (per reference)
                try:
                    code_field = page.get_by_label("Confirmation code", exact=True)
                    code_field.wait_for(state="visible", timeout=15000)
                    code_field.fill(code)  # No click - overlay intercepts pointer events
                    _human_pause(1.0, 2.0)
                    # Click Confirm, handle navigation as success
                    # After OTP fill, click Continue -> profile opens automatically
                    try:
                        continue_btn = page.get_by_role("button", name="Continue", exact=True)
                        continue_btn.wait_for(state="visible", timeout=15000)
                        with print_lock:
                            print(f"{CYAN}[Browser] Clicking Continue{WHITE}")
                        _human_click(page, continue_btn)
                        time.sleep(5.0)  # Human waits for profile to load
                        navigated = True
                    except Exception as e:
                        with print_lock:
                            print(f"{RED}[Browser] Continue click failed: {e}{WHITE}")
                        navigated = False
                    _human_pause(2.0, 3.0)

                    # Check again for login
                    cookies = page.context.cookies()
                    c_user = next((c["value"] for c in cookies if c["name"] == "c_user"), None)
                    if c_user:
                        # Open profile to verify account works
                        try:
                            with print_lock:
                                print(f"{CYAN}[Browser] Opening profile...{WHITE}")
                            page.goto(f"https://www.facebook.com/{c_user}", wait_until="domcontentloaded", timeout=30000)
                            _human_pause(2.0, 3.0)
                            with print_lock:
                                print(f"{GREEN}[Browser] Profile opened: {page.url}{WHITE}")
                            time.sleep(4.0)  # 4s after profile per user
                        except Exception as e:
                            with print_lock:
                                print(f"{YELLOW}[Browser] Profile open skipped: {e}{WHITE}")
                        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                        if counter:
                            counter.update("success")
                        return {
                            "status": "success",
                            "uid": c_user,
                            "password": password,
                            "cookies": cookie_str,
                            "result_line": f"{c_user}|{password}|{cookie_str}",
                        }
                except Exception as e:
                    with print_lock:
                        print(f"{RED}[Browser] Code submission error: {e}{WHITE}")

            if counter:
                counter.update("failed")
            return {"status": "failed", "reason": "verification_required"}

        # Unknown state
        with print_lock:
            print(f"{RED}[Browser] FAILED: Unknown state for {phone_number}{WHITE}")

        if counter:
            counter.update("failed")
        return {"status": "failed", "reason": "unknown_state"}

    except Exception as e:
        with print_lock:
            print(f"{RED}[Browser] ERROR for {phone_number}: {e}{WHITE}")

        if counter:
            counter.update("error")
        return {"status": "error", "reason": str(e)}


def run_browser_mode(numbers, password_config, counter=None):
    """
    Run browser automation for a list of numbers (sequential, one by one).

    Args:
        numbers: List of phone numbers
        password_config: Dict with password settings
        counter: Optional Counter instance
    """
    if not PLAYWRIGHT_AVAILABLE:
        print(f"{RED}Playwright not installed. Run: pip install playwright{WHITE}")
        print(f"{RED}Then run: playwright install chromium{WHITE}")
        return

    from core.password_manager import generate_random_password

    if counter is None:
        counter = Counter()

    def _get_password(cfg):
        if cfg and cfg.get("type") == "fixed" and cfg.get("value"):
            return cfg["value"]
        return generate_random_password()

    with sync_playwright() as p:
        # Launch visible browser (headed) so user can see
        # executable_path: uses manually placed Chromium (bypasses install check)
        import os
        _exe = os.path.expandvars(
            r"C:\Users\Rizvi Lion\AppData\Local\ms-playwright\chromium-1243\chrome-win\chrome.exe"
        )
        _launch_kwargs = dict(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        if os.path.exists(_exe):
            _launch_kwargs["executable_path"] = _exe
        browser = p.chromium.launch(**_launch_kwargs)
        _accounts_since_restart = 0

        try:
            for idx, entry in enumerate(numbers, 1):
                # Restart browser every 4 accounts for fresh fingerprint
                if _accounts_since_restart >= 4:
                    with print_lock:
                        print(f"{YELLOW}[Browser] Restarting browser (every 4 accounts){WHITE}")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    time.sleep(2.0)
                    browser = p.chromium.launch(**_launch_kwargs)
                    _accounts_since_restart = 0
                number, sms_url = _parse_number_entry(entry)
                if not number:
                    continue  # Skip empty/comment lines
                with print_lock:
                    print(f"\n{LINE}")
                    print(f"{CYAN}[{idx}/{len(numbers)}] Processing {number}{WHITE}")
                    if sms_url:
                        print(f"{CYAN}SMS URL: {sms_url[:50]}...{WHITE}")

                # Fresh context per account (incognito-like)
                _vp = random.choice([(1366, 768), (1920, 1080), (1536, 864), (1440, 900), (1280, 720)])
                _cv = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0", "124.0.0.0"])
                _ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_cv} Safari/537.36"
                context = browser.new_context(
                    viewport={"width": _vp[0], "height": _vp[1]},
                    user_agent=_ua,
                    locale="en-US",
                )
                # Fingerprint spoofing: canvas noise + WebGL GPU spoof (per-account random)
                _apply_fingerprint_spoof(context)
                page = context.new_page()

                try:
                    # Generate password for this account
                    password = _get_password(password_config)

                    result = browser_create_account(page, number, password, counter, sms_url)

                    if result["status"] == "success":
                        # Save to output (same format as HTTP version)
                        from core.path_manager import get_output_dir
                        output_dir = get_output_dir()
                        os.makedirs(output_dir, exist_ok=True)
                        with open(os.path.join(output_dir, "browser_accounts.txt"), "a") as f:
                            f.write(result["result_line"] + "\n")

                except Exception as e:
                    with print_lock:
                        print(f"{RED}[Browser] Account {number} error: {e}{WHITE}")
                        print(f"{YELLOW}[Browser] Fix manually, then Enter=retry, 'skip'=next account{WHITE}")
                    if counter:
                        counter.update("error")
                    # Ask user: retry or skip (blocking, user wants manual control)
                    try:
                        choice = input(f"{CYAN}Choice: {WHITE}").strip().lower()
                    except Exception:
                        choice = "skip"
                    if choice == "skip":
                        with print_lock:
                            print(f"{YELLOW}[Browser] Skipping to next account{WHITE}")
                    else:
                        with print_lock:
                            print(f"{CYAN}[Browser] Retrying {number}...{WHITE}")
                        # Retry same account by decrementing loop handled via continue flag
                        # Simple: re-run browser_create_account once more
                        try:
                            result = browser_create_account(page, number, password, counter, sms_url)
                            if result["status"] == "success":
                                from core.path_manager import get_output_dir
                                output_dir = get_output_dir()
                                os.makedirs(output_dir, exist_ok=True)
                                with open(os.path.join(output_dir, "browser_accounts.txt"), "a") as f:
                                    f.write(result["result_line"] + "\n")
                        except Exception as e2:
                            with print_lock:
                                print(f"{RED}[Browser] Retry failed: {e2}{WHITE}")
                finally:
                    # Close context (clear all data for this account)
                    try:
                        context.close()
                    except Exception:
                        pass
                    _accounts_since_restart += 1

                # Pause between accounts (human-like)
                if idx < len(numbers):
                    pause = random.uniform(3, 5)  # Max 7s between accounts per user
                    with print_lock:
                        print(f"{YELLOW}Waiting {pause:.0f}s before next account...{WHITE}")
                    time.sleep(pause)

        finally:
            browser.close()

        # Print summary
        s = counter.summary()
        with print_lock:
            print(f"\n{LINE}")
            print(f" {GREEN}[{RED}●{GREEN}] {WHITE}Browser Mode Completed: {s['checked']} Numbers")
            print(f" {GREEN}[{RED}●{GREEN}] {GREEN}Success: {s['success']}")
            print(f" {GREEN}[{RED}●{GREEN}] {RED}Failed: {s['failed']}")
            print(f"{LINE}")


if __name__ == "__main__":
    # Standalone test mode
    print(f"{CYAN}Browser automation module - standalone test{WHITE}")
    print(f"{YELLOW}This module is imported by main.py in Browser mode.{WHITE}")

    if not PLAYWRIGHT_AVAILABLE:
        print(f"{RED}Playwright not installed.{WHITE}")
        sys.exit(1)

    print(f"{GREEN}Playwright available. Module loaded successfully.{WHITE}")
