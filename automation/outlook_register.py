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
    from playwright_stealth import stealth_sync as _stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False
    _stealth_sync = None

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, LINE
from ui.display import print_lock
from core.counter import Counter
from automation.browser_register import _human_pause, _human_type, _human_mouse_move, _human_scroll

# === Anti-detect pack (Outlook ONLY - reverted from 2026-10-13, restored 2026-10-17 per user) ===


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

def _apply_trace_removal(page):
    """Remove ALL automation traces (Playwright-specific + Selenium leftovers)."""
    try:
        page.add_init_script("""
        ['__playwright', '__pw_manual', '_playwrightBinding',
         '__playwright__binding__', '__webdriver_evaluate',
         '__selenium_evaluate', '__webdriver_script_function',
         'cdc_adoQpoasnfa76pfcZLmcfl_Array', 'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
         'cdc_adoQpoasnfa76pfcZLmcfl_Symbol', 'domAutomation',
         'domAutomationController', '_selenium', 'calledSelenium'
        ].forEach(k => { try { delete window[k]; } catch(_) {} });
        if (!window.chrome) {
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
        }
        try {
            const _oq = Permissions.prototype.query;
            Permissions.prototype.query = function(d) {
                if (d.name === 'notifications')
                    return Promise.resolve({state: 'denied', onchange: null});
                return _oq.call(this, d);
            };
        } catch(_) {}
        """)
    except Exception:
        pass


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
        # Added 2026-10-21: if this email is already taken, say so clearly
        # here instead of failing later with a confusing timeout
        try:
            _em_txt = page.locator("body").inner_text(timeout=5000).lower()
            if "already taken" in _em_txt or "is already an account" in _em_txt:
                with print_lock:
                    print(f"{RED}[Outlook] Email already taken: {email}{WHITE}")
                if counter:
                    counter.update("failed")
                return {"status": "failed", "email": email, "reason": "email_taken"}
        except Exception:
            pass
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
        # Added 2026-10-21: if we are STILL on the password page and Microsoft
        # shows its requirements error, report it here instead of failing
        # mysteriously later on the birthdate step
        try:
            if page.get_by_role("textbox", name="Password").count() > 0:
                _pw_txt = page.locator("body").inner_text(timeout=5000).lower()
                if "passwords must have at least" in _pw_txt or "enter a longer password" in _pw_txt:
                    with print_lock:
                        print(f"{RED}[Outlook] Microsoft rejected the password (requirements not met){WHITE}")
                    if counter:
                        counter.update("failed")
                    return {"status": "failed", "email": email, "reason": "password_rejected"}
        except Exception:
            pass

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
        # Added 2026-10-21: verify BOTH name fields really hold their values.
        # Human typing can silently miss a field; fill() sets the value
        # directly (no click needed), so use it as a safety net.
        try:
            for _fld, _val in ((fn_field, first_name), (ln_field, last_name)):
                try:
                    _cur = _fld.input_value(timeout=3000)
                except Exception:
                    _cur = ""
                if _cur.strip() != _val.strip():
                    _fld.fill(_val)
                    with print_lock:
                        print(f"{YELLOW}[Outlook] Name field auto-fixed with fill(): {_val}{WHITE}")
        except Exception:
            pass
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
        # Added 2026-10-21: if we are STILL on the name page, refill both
        # fields with fill() and try Next once more before giving up
        try:
            if page.get_by_role("textbox", name="First name").count() > 0:
                with print_lock:
                    print(f"{YELLOW}[Outlook] Still on name page - retrying with fill() + Next{WHITE}")
                fn_field.fill(first_name)
                ln_field.fill(last_name)
                page.get_by_role("button", name="Next").first.click()
                _human_pause(3.0, 5.0)
        except Exception:
            pass
        with print_lock:
            print(f"{GREEN}[Outlook] Name: {first_name} {last_name}{WHITE}")

        # Added 2026-10-21: a Microsoft error page (blocked / temporarily
        # unavailable) must not be mistaken for the CAPTCHA step
        try:
            _body_txt = page.locator("body").inner_text(timeout=5000).lower()
            for _phrase in ("temporarily unavailable", "unusual activity",
                            "account creation has been blocked",
                            "we couldn't create your account"):
                if _phrase in _body_txt:
                    with print_lock:
                        print(f"{RED}[Outlook] Microsoft error page: {_phrase}{WHITE}")
                    if counter:
                        counter.update("failed")
                    return {"status": "failed", "email": email,
                            "reason": f"microsoft_error:{_phrase}"}
        except Exception:
            pass

        # Step 5: CAPTCHA - MANUAL (user solves it themselves)
        with print_lock:
            print(f"\n{YELLOW}{'='*50}{WHITE}")
            print(f"{YELLOW}[Outlook] CAPTCHA aya hai - khud solve karo!{WHITE}")
            print(f"{YELLOW}[Outlook] Browser mein press-and-hold karo,{WHITE}")
            print(f"{YELLOW}[Outlook] phir yahan Enter dabao...{WHITE}")
            print(f"{YELLOW}{'='*50}\n{WHITE}")
        try:
            input(f"{CYAN}[Outlook] CAPTCHA solve karke Enter dabao: {WHITE}")
        except Exception:
            pass
        _human_pause(2.0, 3.0)

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


def run_outlook_mode(count, password_config, counter=None, proxy_list=None, proxy_cycle=None):
    """Run Outlook account creation for `count` accounts (sequential).

    Proxy support (Mode 4):
    - proxy_list / proxy_cycle from main.py (get_proxy_list) - round-robin
    - If neither given, auto-loads proxies.txt if present
    - Each account gets the NEXT proxy (per-context, no browser restart needed)
    - Context locale/timezone are aligned to the proxy's country/timezone
    - No proxy = direct connection (old behaviour, fully backward compatible)
    """
    if not PLAYWRIGHT_AVAILABLE:
        print(f"{RED}Playwright not installed. Run: pip install playwright{WHITE}")
        return

    if counter is None:
        counter = Counter()

    # --- Proxy setup ---
    from core.proxy_manager import create_proxy_cycle, format_proxy_for_playwright, load_proxies_from_file
    if proxy_cycle is None and proxy_list:
        proxy_cycle = create_proxy_cycle(proxy_list)
    if proxy_cycle is None and not proxy_list:
        # Standalone call - try proxies.txt directly
        try:
            _file_proxies = load_proxies_from_file()
            if _file_proxies:
                proxy_list = _file_proxies
                proxy_cycle = create_proxy_cycle(proxy_list)
        except Exception:
            pass
    if proxy_list:
        with print_lock:
            print(f"{GREEN}[Outlook] Proxy mode: {len(proxy_list)} proxies loaded, rotation ON{WHITE}")
    else:
        with print_lock:
            print(f"{YELLOW}[Outlook] No proxy - direct connection{WHITE}")

    with sync_playwright() as p:
        from core.browser_launcher import get_browser_choice, launch_browser
        _browser_type = get_browser_choice()
        browser, _is_cloak = launch_browser(p, _browser_type, headless=False)
        _launch_fn = lambda pw: launch_browser(pw, _browser_type, headless=False)[0]
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
                    browser = _launch_fn(p)
                    _accounts_since_restart = 0

                # Pick a random virtual device for this account
                dev = random.choice(VIRTUAL_DEVICES)
                with print_lock:
                    print(f"{CYAN}[Outlook] Virtual device: {dev['name']}{WHITE}")

                # --- Next proxy in rotation (per-account) ---
                proxy_data = next(proxy_cycle) if proxy_cycle else None
                pw_proxy = format_proxy_for_playwright(proxy_data) if proxy_data else None
                context_kwargs = dict(
                    viewport=dev["viewport"],
                    user_agent=dev["user_agent"],
                    device_scale_factor=dev["device_scale_factor"],
                    is_mobile=dev["is_mobile"],
                    has_touch=dev["has_touch"],
                )
                if pw_proxy:
                    context_kwargs["proxy"] = pw_proxy
                    if proxy_data.get("rotating"):
                        # Webshare rotating: IP is assigned server-side per new
                        # connection, so pre-known country/timezone does NOT
                        # apply. Don't force locale/timezone - keep defaults.
                        with print_lock:
                            print(f"{GREEN}[Outlook] Proxy: Webshare ROTATING {pw_proxy['server']} (user: {pw_proxy.get('username','')}) - har account ko nayi IP milegi{WHITE}")
                    else:
                        # Align locale/timezone to proxy location (consistency)
                        try:
                            _loc = (proxy_data.get("language") or proxy_data.get("locale") or "en-US").replace("_", "-")
                            context_kwargs["locale"] = _loc
                            _tz = proxy_data.get("ip_timezone")
                            if not _tz or _tz == "Unknown":
                                _tz = proxy_data.get("timezone")
                            if _tz and _tz != "Unknown":
                                context_kwargs["timezone_id"] = _tz
                        except Exception:
                            pass
                        with print_lock:
                            print(f"{GREEN}[Outlook] Proxy: {pw_proxy['server']} ({proxy_data.get('country','?')}, {context_kwargs.get('timezone_id','?')}){WHITE}")
                try:
                    context = browser.new_context(**context_kwargs)
                except Exception as e:
                    with print_lock:
                        print(f"{RED}[Outlook] Proxy/context failed ({e}) - skipping this account, next proxy will be used{WHITE}")
                    if counter:
                        counter.update("error")
                    continue
                _apply_fingerprint_spoof(context)
                page = context.new_page()
                # Apply stealth: playwright-stealth + full trace removal
                if _HAS_STEALTH and _stealth_sync:
                    try:
                        _stealth_sync(page)
                    except Exception:
                        pass
                _apply_trace_removal(page)
                # Added 2026-10-21: cap every action at 15s (was 30s) so one
                # stuck field can never hang the whole run silently
                try:
                    page.set_default_timeout(15000)
                except Exception:
                    pass
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
