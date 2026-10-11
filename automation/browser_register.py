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
    like a human typing.
    """
    element = page.locator(selector)
    element.click()
    _human_pause(0.3, 0.8)
    for char in text:
        element.press_sequentially(char, delay=random.randint(min_delay, max_delay))
    _human_pause(0.5, 1.5)


def _select_birthday(page, day, month, year):
    """Select birthday from Facebook's combobox dropdowns."""
    # Month combobox
    month_box = page.get_by_label("Month:")
    month_box.click()
    _human_pause(0.5, 1.0)
    month_box.select_option(label=month)
    _human_pause(0.5, 1.0)

    # Day combobox
    day_box = page.get_by_label("Day:")
    day_box.click()
    _human_pause(0.5, 1.0)
    day_box.select_option(label=str(day))
    _human_pause(0.5, 1.0)

    # Year combobox
    year_box = page.get_by_label("Year:")
    year_box.click()
    _human_pause(0.5, 1.0)
    year_box.select_option(label=str(year))
    _human_pause(0.5, 1.0)


def _select_gender(page, gender):
    """Click gender selection (Female/Male/Custom)."""
    if gender.lower() == "female":
        page.get_by_label("Female").click()
    elif gender.lower() == "male":
        page.get_by_label("Male").click()
    else:
        # Default to Female for random
        page.get_by_label("Female").click()
    _human_pause(0.5, 1.0)


def _parse_number_entry(entry):
    """Parse 'number|otp_url' format. Returns (number, otp_url or None)."""
    entry = entry.strip()
    if "|" in entry:
        parts = entry.split("|", 1)
        return parts[0].strip(), parts[1].strip()
    return entry, None


def _fetch_otp_from_url(page, sms_url, timeout=120):
    """
    Open SMS URL in a new tab and poll for OTP code.
    Looks for 4-8 digit codes in page text, preferring Facebook SMS.
    Returns the code or None.
    """
    import re

    context = page.context
    sms_page = context.new_page()
    try:
        sms_page.goto(sms_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass

    start = time.time()
    seen_codes = set()
    while time.time() - start < timeout:
        try:
            sms_page.reload(wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(3)

        try:
            text = sms_page.inner_text("body")
        except Exception:
            continue

        # Look for Facebook SMS with code
        # Pattern: 5-8 digit code, often near "Facebook" or "FB"
        text_lower = text.lower()
        if "facebook" in text_lower or "fb-" in text_lower:
            codes = re.findall(r'\b\d{5,8}\b', text)
            for code in codes:
                if code not in seen_codes:
                    seen_codes.add(code)
                    # Prefer codes near Facebook mention
                    idx = text_lower.find("facebook")
                    if idx == -1:
                        idx = text_lower.find("fb-")
                    code_idx = text.find(code)
                    if abs(code_idx - idx) < 200:  # Within 200 chars
                        sms_page.close()
                        return code
            # Fallback: return the most recent code found
            if codes:
                sms_page.close()
                return codes[-1]

    try:
        sms_page.close()
    except Exception:
        pass
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
        page.goto("https://www.facebook.com/reg/", wait_until="domcontentloaded")
        _human_pause(2.0, 4.0)

        # Fill first name
        _human_type(page, 'input[name="firstname"]', first_name)

        # Fill last name
        _human_type(page, 'input[name="lastname"]', last_name)

        # Fill phone number
        _human_type(page, 'input[name="reg_email__"]', phone_number)

        # Fill password
        _human_type(page, 'input[name="reg_passwd__"]', password)

        # Select birthday
        _select_birthday(page, birth_date.day, birth_month, birth_date.year)

        # Select gender
        _select_gender(page, gender)

        _human_pause(1.0, 2.0)

        # Submit
        with print_lock:
            print(f"{YELLOW}[Browser] Submitting form...{WHITE}")
        page.locator('button[name="websubmit"]').click()

        # Wait for result - either success (logged in) or OTP/code page
        _human_pause(3.0, 5.0)

        # Check if we're logged in (c_user cookie or profile URL)
        cookies = page.context.cookies()
        c_user = next((c["value"] for c in cookies if c["name"] == "c_user"), None)

        if c_user:
            # Success - save account
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            result = f"{c_user}|{password}|{cookie_str}"

            with print_lock:
                print(f"{GREEN}[Browser] SUCCESS: {c_user}{WHITE}")

            if counter:
                counter.increment("success")

            return {
                "status": "success",
                "uid": c_user,
                "password": password,
                "cookies": cookie_str,
                "result_line": result,
            }

        # Check if OTP/code page appeared
        page_content = page.content().lower()
        if "code" in page_content or "confirm" in page_content or "otp" in page_content:
            code = None

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
                # Try to find code input and submit
                try:
                    code_input = page.locator('input[id="code_in_cliff"], input[name="code"]')
                    if code_input.count() > 0:
                        _human_type(page, 'input[id="code_in_cliff"], input[name="code"]', code)
                        _human_pause(1.0, 2.0)
                        # Click continue/submit
                        page.locator('button[type="submit"]').first.click()
                        _human_pause(3.0, 5.0)

                        # Check again for login
                        cookies = page.context.cookies()
                        c_user = next((c["value"] for c in cookies if c["name"] == "c_user"), None)
                        if c_user:
                            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                            if counter:
                                counter.increment("success")
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
                counter.increment("failed")
            return {"status": "failed", "reason": "verification_required"}

        # Unknown state
        with print_lock:
            print(f"{RED}[Browser] FAILED: Unknown state for {phone_number}{WHITE}")

        if counter:
            counter.increment("failed")
        return {"status": "failed", "reason": "unknown_state"}

    except Exception as e:
        with print_lock:
            print(f"{RED}[Browser] ERROR for {phone_number}: {e}{WHITE}")

        if counter:
            counter.increment("error")
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
