"""Full test: Create ONE Facebook account using REAL Google Chrome.
Run: python test_real_chrome_full.py

Uses the first number from Number_List.txt.
Separate test file - does NOT touch the main tool.
"""
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from automation.browser_register import (
    browser_create_account,
    _apply_fingerprint_spoof,
    _parse_number_entry,
)
from core.password_manager import generate_random_password
from ui.colors import GREEN, RED, WHITE, CYAN

print(f"{CYAN}=== Real Chrome Full Account Test ==={WHITE}")

# Read first number from Number_List.txt
num_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Number_List.txt")
if not os.path.exists(num_file):
    print(f"{RED}Number_List.txt not found!{WHITE}")
    sys.exit(1)

with open(num_file) as f:
    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

if not lines:
    print(f"{RED}No numbers in Number_List.txt!{WHITE}")
    sys.exit(1)

number, sms_url = _parse_number_entry(lines[0])
password = generate_random_password()
print(f"{CYAN}Testing with: {number}{WHITE}")
print(f"{CYAN}Password: {password}{WHITE}")

try:
    with sync_playwright() as p:
        print(f"{CYAN}Launching REAL Google Chrome...{WHITE}")
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        print(f"{GREEN}Real Chrome launched!{WHITE}")

        _vp = random.choice([(1366, 768), (1920, 1080), (1536, 864)])
        _cv = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0"])
        _ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_cv} Safari/537.36"
        context = browser.new_context(
            viewport={"width": _vp[0], "height": _vp[1]},
            user_agent=_ua,
            locale="en-US",
        )
        _apply_fingerprint_spoof(context, _cv, _vp)
        page = context.new_page()

        print(f"{CYAN}Creating account...{WHITE}")
        result = browser_create_account(page, number, password, counter=None, sms_url=sms_url)
        print(f"\n{CYAN}{'='*50}{WHITE}")
        if result.get("status") == "success":
            print(f"{GREEN}[Test] SUCCESS: UID {result.get('uid')}{WHITE}")
        else:
            print(f"{RED}[Test] FAILED: {result.get('number')} - {result.get('reason')}{WHITE}")
        print(f"{CYAN}{'='*50}{WHITE}")

        context.close()
        browser.close()
except Exception as e:
    print(f"{RED}FAILED: {e}{WHITE}")
    import traceback
    traceback.print_exc()
