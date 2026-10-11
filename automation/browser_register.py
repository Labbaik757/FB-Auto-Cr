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
    """Random pause to mimic human behavior."""
    time.sleep(random.uniform(min_s, max_s))


def _human_type(page, selector, text, min_delay=80, max_delay=250):
    """
    Type text character by character with random delays,
    like a human typing. Accepts CSS selector string or Locator.
    """
    element = selector if hasattr(selector, "click") else page.locator(selector)
    element.click()
    _human_pause(0.3, 0.8)
    for char in text:
        element.press_sequentially(char, delay=random.randint(min_delay, max_delay))
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


def _click_resend_twice(page):
    """Click resend code button 2 times with pauses (triggers OTP delivery)."""
    resend_selectors = [
        'button:has-text("Resend")',
        'a:has-text("Resend")',
        '[role="button"]:has-text("Resend")',
        'button:has-text("Send code again")',
        'a:has-text("Send again")',
        '[role="button"]:has-text("Send again")',
        'a:has-text("Didn\'t get the code")',
        'button:has-text("Resend SMS")',
        'a:has-text("Resend SMS")',
    ]
    clicked = 0
    for attempt in range(2):
        for sel in resend_selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=3000):
                    btn.click()
                    clicked += 1
                    with print_lock:
                        print(f"{CYAN}[Browser] Resend clicked ({clicked}/2){WHITE}")
                    _human_pause(3.0, 5.0)
                    break
            except Exception:
                continue
        if clicked >= 2:
            break
        _human_pause(2.0, 3.0)
    return clicked


def _fetch_otp_from_url(page, sms_url, timeout=180, interval=5):
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

    # Generate identity
    first_name = fake.first_name()
    last_name = fake.last_name()
    gender = random.choice(["Female", "Male"])

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
        text_inputs = page.locator('input[type="text"]')
        pwd_inputs = page.locator('input[type="password"]')
        _human_type(page, text_inputs.nth(0), first_name)
        _human_type(page, text_inputs.nth(1), last_name)
        _human_type(page, text_inputs.nth(2), phone_number)
        _human_type(page, pwd_inputs.nth(0), password)

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

            # Click resend twice to trigger OTP delivery, then auto-fetch
            _click_resend_twice(page)

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

            # Fallback to manual input
            if not code:
                with print_lock:
                    print(f"{YELLOW}[Browser] Verification code required.{WHITE}")
                    print(f"{YELLOW}Enter the code sent to {phone_number} (or 'skip' to skip):{WHITE}")
                code = input(f"{CYAN}Code: {WHITE}").strip()

            if code.lower() != "skip" and code:
                # Fill OTP and confirm (per reference)
                try:
                    code_field = page.get_by_label("Confirmation code", exact=True)
                    code_field.wait_for(state="visible", timeout=15000)
                    _human_type(page, code_field, code)
                    _human_pause(1.0, 2.0)
                    # Click Confirm, handle navigation as success
                    try:
                        # First try Confirm, then Continue
                        confirm_btn = None
                        for btn_name in ["Confirm", "Continue"]:
                            try:
                                b = page.get_by_role("button", name=btn_name, exact=True)
                                b.wait_for(state="visible", timeout=8000)
                                confirm_btn = b
                                with print_lock:
                                    print(f"{CYAN}[Browser] Found button: {btn_name}{WHITE}")
                                break
                            except Exception:
                                continue
                        if not confirm_btn:
                            raise Exception("Neither Confirm nor Continue found")
                        # Wait for navigation after click (success = leave confirm page)
                        with page.expect_navigation(timeout=15000, wait_until="domcontentloaded"):
                            confirm_btn.click()
                        navigated = True
                    except Exception as nav_e:
                        # Check if we navigated anyway (success)
                        try:
                            cur = page.url
                            if "confirmemail" not in cur and "checkpoint" not in cur:
                                navigated = True
                                with print_lock:
                                    print(f"{GREEN}[Browser] Navigated after confirm: {cur}{WHITE}")
                            else:
                                navigated = False
                        except Exception:
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
                            _human_pause(2.0, 4.0)
                            with print_lock:
                                print(f"{GREEN}[Browser] Profile opened: {page.url}{WHITE}")
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

        try:
            for idx, entry in enumerate(numbers, 1):
                number, sms_url = _parse_number_entry(entry)
                if not number:
                    continue  # Skip empty/comment lines
                with print_lock:
                    print(f"\n{LINE}")
                    print(f"{CYAN}[{idx}/{len(numbers)}] Processing {number}{WHITE}")
                    if sms_url:
                        print(f"{CYAN}SMS URL: {sms_url[:50]}...{WHITE}")

                # Fresh context per account (incognito-like)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                )
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

                finally:
                    # Close context (clear all data for this account)
                    context.close()

                # Pause between accounts (human-like)
                if idx < len(numbers):
                    pause = random.uniform(10, 20)
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
