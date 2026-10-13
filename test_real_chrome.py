"""Test: Playwright with REAL Google Chrome (channel="chrome").
Run: python test_real_chrome.py
This does NOT touch the main tool. Only checks if real Chrome launches
and Facebook registration form loads.
"""
from playwright.sync_api import sync_playwright
import time

print("Launching REAL Google Chrome via Playwright...")
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        print("SUCCESS: Real Chrome launched!")

        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = context.new_page()
        page.goto("https://www.facebook.com/r.php", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Check form fields exist
        inputs = page.locator('input[type="text"]').count()
        pwd = page.locator('input[type="password"]').count()
        print(f"Text inputs found: {inputs}, Password inputs found: {pwd}")

        if inputs >= 3 and pwd >= 1:
            print("SUCCESS: Facebook registration form loaded correctly!")
        else:
            print("WARNING: Form fields not found as expected.")

        print("\nBrowser will stay open 10 seconds for visual check...")
        time.sleep(10)
        browser.close()
        print("Test complete.")
except Exception as e:
    print(f"FAILED: {e}")
    print("\nReal Chrome not found or launch failed.")
    print("Make sure Google Chrome is installed on this PC.")
