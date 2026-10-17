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
from automation.browser_register import _human_pause, _human_click, _human_type


def _gen_email_username(fake):
    """Generate a random Outlook username (like lilydodson345)."""
    base = fake.first_name().lower() + fake.last_name().lower()
    # Clean non-alpha
    base = "".join(c for c in base if c.isalpha())
    num = random.randint(100, 9999)
    return f"{base}{num}"


def _press_and_hold_captcha(page):
    """Human-like press-and-hold for Arkose verification.
    Scripted holds get rejected; slow human-style works.
    Returns True if verification passed."""
    try:
        # Locate the nested iframe chain
        outer = page.frame_locator('iframe[name="Verification challenge"]')
        inner = outer.frame_locator('iframe[name="Human verification challenge"]')
        # Find the press-and-hold button
        btn = inner.get_by_role("button", name="Press and hold").first
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
            combo.click()
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
                    combo.click()
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
            for idx in range(1, count + 1):
                with print_lock:
                    print(f"\n{LINE}")
                    print(f"{CYAN}[{idx}/{count}] Creating Outlook account...{WHITE}")

                context = browser.new_context()
                page = context.new_page()

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
                    pause = random.uniform(3, 5)
                    with print_lock:
                        print(f"{YELLOW}Waiting {pause:.0f}s before next...{WHITE}")
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
