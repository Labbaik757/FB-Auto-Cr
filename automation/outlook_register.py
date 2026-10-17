"""
Outlook/Hotmail account creation via Playwright (Mode 4).

LIVE-VERIFIED selectors (2026-10-17, real account created: lilydodson345@outlook.com).
Flow: signup.live.com -> Email -> Password -> Birthdate -> Name -> Press-and-hold CAPTCHA -> done.

Usage:
    from automation.outlook_register import run_outlook_mode
    run_outlook_mode(count, password_config, counter)
"""
import os
import sys
import time
import random

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
from automation.browser_register import _human_pause, _human_type
import math

# === Anti-detect pack (Outlook ONLY - reverted from 2026-10-13, restored 2026-10-17 per user) ===

def _human_mouse_move(page, x, y, steps=20):
    """Curved human-like mouse movement."""
    try:
        cur = page.evaluate("() => ({x: 0, y: 0})")
        # Simple curved path
        for i in range(1, steps + 1):
            t = i / steps
            # Bezier-ish curve with slight randomness
            mx = cur["x"] + (x - cur["x"]) * t + random.uniform(-5, 5) * math.sin(t * math.pi)
            my = cur["y"] + (y - cur["y"]) * t + random.uniform(-5, 5) * math.sin(t * math.pi)
            page.mouse.move(mx, my, steps=1)
            time.sleep(random.uniform(0.01, 0.03))
    except Exception:
        try:
            page.mouse.move(x, y)
        except Exception:
            pass

def _human_click(page, locator):
    """Human click: move mouse curved to element, then click."""
    try:
        box = locator.bounding_box(timeout=5000)
        if box:
            cx = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            cy = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            _human_mouse_move(page, cx, cy)
            time.sleep(random.uniform(0.1, 0.3))
        locator.click(timeout=10000)
    except Exception:
        try:
            locator.click(force=True, timeout=10000)
        except Exception:
            pass

def _human_type_typos(page, locator, text):
    """Type with occasional typos (15% chance per char) then correct."""
    try:
        locator.click()
    except Exception:
        pass
    time.sleep(random.uniform(0.2, 0.5))
    for ch in text:
        # 15% typo chance
        if random.random() < 0.15 and ch.isalpha():
            wrong = random.choice("abcdefghijklmnopqrstuvwxyz")
            page.keyboard.type(wrong)
            time.sleep(random.uniform(0.08, 0.2))
            page.keyboard.press("Backspace")
            time.sleep(random.uniform(0.1, 0.25))
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.08, 0.25))
    time.sleep(random.uniform(0.3, 0.7))

def _apply_fingerprint_spoof(context):
    """Apply fingerprint spoofing via JS (canvas, WebGL, navigator, etc)."""
    seed = random.randint(1, 10)
    gpus = [
        "NVIDIA GeForce GTX 1660 SUPER",
        "AMD Radeon RX 580",
        "Intel UHD Graphics 630",
        "NVIDIA GeForce RTX 3060",
        "AMD Radeon RX 5700 XT",
    ]
    gpu = random.choice(gpus)
    js = f"""
    // Canvas noise
    (function() {{
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(...args) {{
            const ctx = this.getContext('2d');
            if (ctx) {{
                const imgData = ctx.getImageData(0, 0, this.width, this.height);
                for (let i = 0; i < imgData.data.length; i += 4) {{
                    imgData.data[i] += Math.floor(Math.random() * {seed}) - {seed // 2};
                }}
                ctx.putImageData(imgData, 0, 0);
            }}
            return origToDataURL.apply(this, args);
        }};
    }})();
    // WebGL GPU spoof
    (function() {{
        const origGetParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return "Google Inc. (NVIDIA)";
            if (param === 37446) return "{gpu}";
            return origGetParam.apply(this, arguments);
        }};
    }})();
    // navigator.webdriver -> false
    Object.defineProperty(navigator, 'webdriver', {{ get: () => false }});
    // Plugins
    Object.defineProperty(navigator, 'plugins', {{ get: () => [1,2,3,4] }});
    // AudioContext noise
    (function() {{
        const origGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function(...args) {{
            const data = origGetChannelData.apply(this, args);
            for (let i = 0; i < data.length; i += 100) {{
                data[i] += (Math.random() - 0.5) * 0.001;
            }}
            return data;
        }};
    }})();
    // Screen spoof (match common viewport)
    // Fonts check always true
    (function() {{
        const origCheck = document.fonts.check;
        document.fonts.check = function(...args) {{ return true; }};
    }})();
    """
    try:
        context.add_init_script(js)
    except Exception:
        pass

# Virtual device profiles - each account gets a different device fingerprint
VIRTUAL_DEVICES = [
    {"name": "Desktop Chrome Win", "viewport": {"width": 1920, "height": 1080},
     "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "device_scale_factor": 1, "is_mobile": False, "has_touch": False},
    {"name": "Desktop Chrome Win 2", "viewport": {"width": 1366, "height": 768},
     "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
     "device_scale_factor": 1, "is_mobile": False, "has_touch": False},
    {"name": "iPhone 14", "viewport": {"width": 390, "height": 844},
     "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "device_scale_factor": 3, "is_mobile": True, "has_touch": True},
    {"name": "Pixel 7", "viewport": {"width": 412, "height": 915},
     "user_agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
     "device_scale_factor": 2.6, "is_mobile": True, "has_touch": True},
    {"name": "Samsung Galaxy", "viewport": {"width": 360, "height": 800},
     "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
     "device_scale_factor": 3, "is_mobile": True, "has_touch": True},
    {"name": "iPad", "viewport": {"width": 820, "height": 1180},
     "user_agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "device_scale_factor": 2, "is_mobile": True, "has_touch": True},
]

def _launch_real_chrome(p):
    """Launch real Chrome browser (not Chromium)."""
    try:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        with print_lock:
            print(f"{CYAN}[Outlook] Real Chrome launched{WHITE}")
        return browser
    except Exception as e:
        with print_lock:
            print(f"{YELLOW}[Outlook] Real Chrome failed ({e}), falling back to Chromium{WHITE}")
        _exe = os.path.expandvars(
            r"C:\Users\Rizvi Lion\AppData\Local\ms-playwright\chromium-1243\chrome-win\chrome.exe"
        )
        kwargs = dict(headless=False, args=["--disable-blink-features=AutomationControlled"])
        if os.path.exists(_exe):
            kwargs["executable_path"] = _exe
        return p.chromium.launch(**kwargs)


def _gen_email_username(fake):
    """Generate a random Outlook username with varied patterns."""
    first = "".join(c for c in fake.first_name().lower() if c.isalpha())
    last = "".join(c for c in fake.last_name().lower() if c.isalpha())
    num = random.randint(10, 9999)
    pattern = random.choice([
        f"{first}{last}{num}",           # johndoe123
        f"{first}.{last}{num}",          # john.doe123
        f"{first}{num}",                 # john123
        f"{first}_{last}{num}",          # john_doe123
        f"{last}{first}{num}",           # doejohn123
    ])
    return pattern


def _press_and_hold_captcha(page):
    """Human-like press-and-hold for Arkose verification.
    Scripted holds get rejected; slow human-style works.
    Returns True if verification passed."""
    try:
        # Wait for challenge heading first (iframe takes time to load)
        try:
            page.get_by_text("Let's prove you're human").first.wait_for(state="visible", timeout=15000)
        except Exception:
            pass
        _human_pause(2.0, 3.0)
        # Locate the nested iframe chain
        # NOTE: "Verification challenge" is the title attribute, NOT name attribute
        outer = page.frame_locator('iframe[title="Verification challenge"]')
        inner = outer.frame_locator('iframe[title="Human verification challenge"]')
        # Find the press-and-hold button
        btn = inner.get_by_role("button", name="Press and hold").first
        try:
            btn.wait_for(state="visible", timeout=15000)
        except Exception:
            # Fallback: Arkose URL-based locator (more reliable)
            with print_lock:
                print(f"{YELLOW}[Outlook] Trying Arkose URL fallback...{WHITE}")
            outer = page.frame_locator('iframe[src*="arkoselabs"]')
            btn = outer.get_by_role("button", name="Press and hold").first
            btn.wait_for(state="visible", timeout=15000)
        with print_lock:
            print(f"{CYAN}[Outlook] CAPTCHA found, doing human-like press-and-hold...{WHITE}")

        # Human-like: move cursor to button slowly, hover, then hold
        box = btn.bounding_box(timeout=10000)
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            # Slow cursor approach (human-like)
            page.mouse.move(cx + random.randint(50, 150), cy + random.randint(30, 80), steps=10)
            time.sleep(random.uniform(0.5, 1.0))
            page.mouse.move(cx, cy, steps=15)
            time.sleep(random.uniform(0.8, 1.5))  # Hover pause

        # Press and hold for ~10 seconds with slight movement (human tremor)
        btn_handle = btn.element_handle(timeout=10000)
        box = btn_handle.bounding_box()
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        hold_time = random.uniform(9.5, 11.0)
        start = time.time()
        while time.time() - start < hold_time:
            # Tiny human-like tremor during hold
            page.mouse.move(cx + random.uniform(-2, 2), cy + random.uniform(-2, 2), steps=1)
            time.sleep(0.3)
        # Smooth release
        time.sleep(random.uniform(0.3, 0.6))
        page.mouse.up()
        with print_lock:
            print(f"{CYAN}[Outlook] Hold released, waiting for verification...{WHITE}")
        time.sleep(random.uniform(3.0, 5.0))

        # Check if verification passed (page should advance past CAPTCHA)
        try:
            page.wait_for_url(lambda url: "signup.live.com" not in url or "challenge" not in url.lower(), timeout=15000)
        except Exception:
            pass
        # If we're no longer on the challenge, it passed
        cur = page.url.lower()
        if "challenge" not in cur and "verify" not in cur:
            return True
        # Also check: challenge iframe gone = passed
        try:
            if btn.count() == 0:
                return True
        except Exception:
            return True
        with print_lock:
            print(f"{YELLOW}[Outlook] CAPTCHA may need retry{WHITE}")
        return False
    except Exception as e:
        with print_lock:
            print(f"{RED}[Outlook] CAPTCHA failed: {e}{WHITE}")
        return False


def outlook_create_account(page, password_config, counter=None):
    """Create a single Outlook account. Returns dict with status."""
    from core.password_manager import generate_random_password
    fake = Faker()

    # Generate identity (same style as Facebook)
    first_name = fake.first_name()
    last_name = fake.last_name()
    username = _gen_email_username(fake)
    email = f"{username}@outlook.com"

    # Birthday: 1992-2000 range (like Facebook requirement)
    birth_year = random.randint(1992, 2000)
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    month_name = months[birth_month - 1]
    # Random country for each account (different every time)
    countries = ["United States", "United Kingdom", "Canada", "Australia", "Pakistan",
                 "India", "Germany", "France", "Netherlands", "Spain", "Italy",
                 "United Arab Emirates", "Saudi Arabia", "Turkey", "Malaysia",
                 "Singapore", "New Zealand", "Ireland", "Sweden", "Norway"]
    country_name = random.choice(countries)

    # Password: same system as Facebook
    if password_config and password_config.get("type") == "fixed" and password_config.get("value"):
        password = password_config["value"]
    else:
        password = generate_random_password()

    try:
        with print_lock:
            print(f"\n{CYAN}[Outlook] Creating {email}...{WHITE}")

        # Step 1: Email
        page.goto("https://signup.live.com/signup?lic=1", wait_until="domcontentloaded", timeout=30000)
        _human_pause(2.0, 3.0)
        # Random "reading the page" pause (human-like)
        time.sleep(random.uniform(1.0, 3.0))
        email_field = page.get_by_role("textbox", name="Email").first
        email_field.wait_for(state="visible", timeout=15000)
        _human_type(page, email_field, email)
        _human_pause(1.0, 2.0)
        page.get_by_role("button", name="Next").first.click()
        _human_pause(2.0, 3.0)
        with print_lock:
            print(f"{GREEN}[Outlook] Email entered: {email}{WHITE}")

        # Step 2: Password
        pwd_field = page.get_by_role("textbox", name="Password").first
        pwd_field.wait_for(state="visible", timeout=15000)
        _human_type(page, pwd_field, password)
        _human_pause(1.0, 2.0)
        page.get_by_role("button", name="Next").first.click()
        _human_pause(2.5, 4.0)
        # Verify we moved past password step
        try:
            pwd_still = page.get_by_role("textbox", name="Password").count() > 0
            if pwd_still:
                with print_lock:
                    print(f"{YELLOW}[Outlook] Password Next didn't advance, retrying...{WHITE}")
                page.get_by_role("button", name="Next").first.click()
                _human_pause(3.0, 5.0)
        except Exception:
            pass
        with print_lock:
            print(f"{GREEN}[Outlook] Password entered{WHITE}")

        # Step 3: Birthdate (+ random country)
        def _select_combo(combo_name, option_name):
            """Click combobox, click option, verify selection took effect."""
            combo = page.get_by_role("combobox", name=combo_name).first
            combo.wait_for(state="visible", timeout=15000)
            # Force click: floating label overlays the button and intercepts normal clicks
            combo.click(force=True)
            _human_pause(0.8, 1.5)
            opt = page.get_by_role("option", name=option_name, exact=True).first
            opt.wait_for(state="visible", timeout=10000)
            opt.scroll_into_view_if_needed(timeout=5000)
            _human_pause(0.3, 0.6)
            opt.click()
            _human_pause(0.8, 1.2)
            # Verify: combobox should now show the selected value
            try:
                val = combo.input_value(timeout=3000)
                if option_name.lower() not in val.lower() and val.strip():
                    with print_lock:
                        print(f"{YELLOW}[Outlook] Combo '{combo_name}' shows '{val}', retrying...{WHITE}")
                    combo.click(force=True)
                    _human_pause(0.8, 1.2)
                    page.get_by_role("option", name=option_name, exact=True).first.click()
                    _human_pause(0.8, 1.2)
            except Exception:
                pass
            page.keyboard.press("Escape")
            _human_pause(0.5, 1.0)

        # Country/Region (different for every account)
        _select_combo("Country/Region", country_name)
        with print_lock:
            print(f"{GREEN}[Outlook] Country: {country_name}{WHITE}")
        # Birth month
        _select_combo("Birth month", month_name)
        # Birth day
        _select_combo("Birth day", str(birth_day))
        # Birth year spinbutton: clear first, then type
        year_field = page.get_by_role("spinbutton", name="Birth year").first
        year_field.wait_for(state="visible", timeout=15000)
        year_field.click()
        _human_pause(0.3, 0.6)
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.press("Backspace")
        _human_pause(0.3, 0.6)
        _human_type(page, year_field, str(birth_year))
        _human_pause(1.0, 2.0)
        # Click Next and VERIFY we actually advanced
        page.get_by_role("button", name="Next").first.click()
        _human_pause(2.5, 4.0)
        # If still on birthdate page, the Next didn't work - report it
        try:
            still_here = page.get_by_role("combobox", name="Birth month").count() > 0
            if still_here:
                with print_lock:
                    print(f"{RED}[Outlook] STUCK: Still on birthdate page after Next!{WHITE}")
                    print(f"{YELLOW}[Outlook] Trying Next once more...{WHITE}")
                page.get_by_role("button", name="Next").first.click()
                _human_pause(3.0, 5.0)
        except Exception:
            pass
        with print_lock:
            print(f"{GREEN}[Outlook] Birthdate: {month_name} {birth_day}, {birth_year}{WHITE}")

        # Step 4: Name
        fn_field = page.get_by_role("textbox", name="First name").first
        fn_field.wait_for(state="visible", timeout=15000)
        _human_type(page, fn_field, first_name)
        ln_field = page.get_by_role("textbox", name="Last name").first
        _human_type(page, ln_field, last_name)
        # Uncheck marketing checkbox (pre-checked by default)
        try:
            checkbox = page.get_by_role("checkbox", name="I would like information, tips, and offers about Microsoft products and services.").first
            if checkbox.count() > 0 and checkbox.is_checked(timeout=3000):
                checkbox.uncheck()
                with print_lock:
                    print(f"{CYAN}[Outlook] Marketing checkbox unchecked{WHITE}")
        except Exception:
            pass
        _human_pause(1.0, 2.0)
        page.get_by_role("button", name="Next").first.click()
        _human_pause(3.0, 5.0)
        with print_lock:
            print(f"{GREEN}[Outlook] Name: {first_name} {last_name}{WHITE}")

        # Step 5: Press-and-hold CAPTCHA
        if not _press_and_hold_captcha(page):
            with print_lock:
                print(f"{YELLOW}[Outlook] CAPTCHA needs manual solve - waiting 30s...{WHITE}")
            time.sleep(30)
        _human_pause(3.0, 5.0)

        # Step 6: Check result (account created automatically after verification)
        cur_url = page.url.lower()
        if "account.live.com" in cur_url or "outlook.live.com" in cur_url:
            with print_lock:
                print(f"{GREEN}[Outlook] SUCCESS: {email}{WHITE}")
            if counter:
                counter.update("success")
            return {
                "status": "success",
                "email": email,
                "password": password,
                "result_line": f"{email}|{password}",
            }

        with print_lock:
            print(f"{YELLOW}[Outlook] Unclear state, URL: {page.url}{WHITE}")
        if counter:
            counter.update("failed")
        return {"status": "failed", "email": email, "reason": "unclear_state"}

    except Exception as e:
        with print_lock:
            print(f"{RED}[Outlook] ERROR for {email}: {e}{WHITE}")
        if counter:
            counter.update("error")
        return {"status": "error", "email": email, "reason": str(e)}


def run_outlook_mode(count, password_config, counter=None):
    """Run Outlook account creation for `count` accounts (sequential)."""
    if not PLAYWRIGHT_AVAILABLE:
        print(f"{RED}Playwright not installed. Run: pip install playwright{WHITE}")
        return

    if counter is None:
        counter = Counter()

    with sync_playwright() as p:
        browser = _launch_real_chrome(p)
        _accounts_since_restart = 0

        try:
            for idx in range(1, count + 1):
                with print_lock:
                    print(f"\n{LINE}")
                    print(f"{CYAN}[{idx}/{count}] Creating Outlook account...{WHITE}")

                # Restart browser every 4 accounts (fresh fingerprint)
                if _accounts_since_restart >= 4:
                    with print_lock:
                        print(f"{CYAN}[Outlook] Restarting browser (4 accounts done)...{WHITE}")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    time.sleep(random.uniform(1.5, 3.0))
                    browser = _launch_real_chrome(p)
                    _accounts_since_restart = 0

                # Pick a random virtual device for this account
                dev = random.choice(VIRTUAL_DEVICES)
                with print_lock:
                    print(f"{CYAN}[Outlook] Virtual device: {dev['name']}{WHITE}")
                context = browser.new_context(
                    viewport=dev["viewport"],
                    user_agent=dev["user_agent"],
                    device_scale_factor=dev["device_scale_factor"],
                    is_mobile=dev["is_mobile"],
                    has_touch=dev["has_touch"],
                )
                _apply_fingerprint_spoof(context)
                page = context.new_page()
                _accounts_since_restart += 1

                try:
                    result = outlook_create_account(page, password_config, counter)
                    if result["status"] == "success":
                        from core.path_manager import get_output_dir
                        output_dir = get_output_dir()
                        os.makedirs(output_dir, exist_ok=True)
                        with open(os.path.join(output_dir, "outlook_accounts.txt"), "a") as f:
                            f.write(result["result_line"] + "\n")
                except Exception as e:
                    with print_lock:
                        print(f"{RED}[Outlook] Account error: {e}{WHITE}")
                    if counter:
                        counter.update("error")
                finally:
                    try:
                        context.close()
                    except Exception:
                        pass

                if idx < count:
                    pause = random.uniform(30, 60)
                    with print_lock:
                        print(f"{YELLOW}Waiting {pause:.0f}s before next (anti-block)...{WHITE}")
                    time.sleep(pause)
        finally:
            browser.close()

        s = counter.summary()
        with print_lock:
            print(f"\n{LINE}")
            print(f" {GREEN}[{RED}●{GREEN}] {WHITE}Outlook Mode Completed: {s['checked']}")
            print(f" {GREEN}[{RED}●{GREEN}] {GREEN}Success: {s['success']}")
            print(f" {GREEN}[{RED}●{GREEN}] {RED}Failed: {s['failed']}")
            print(f"{LINE}")


if __name__ == "__main__":
    print(f"{CYAN}Outlook automation module - standalone test{WHITE}")
