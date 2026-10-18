"""
Test: playwright-stealth + version-matched UA + full trace removal.
Run: python test_stealth.py
"""
import random
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed")
    sys.exit(1)

try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    print("WARNING: playwright-stealth not installed (pip install playwright-stealth)")

# Recent Chrome versions (matched UA - not old 120-124)
CHROME_VERSIONS = ["131.0.6778.264", "131.0.6778.205", "132.0.6834.160",
                   "132.0.6834.110", "133.0.6943.141", "133.0.6943.126",
                   "134.0.6998.117", "134.0.6998.89"]

def get_test_fingerprint():
    """Generate a consistent fingerprint for this test session."""
    ver = random.choice(CHROME_VERSIONS)
    major = ver.split(".")[0]
    ua = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          f"AppleWebKit/537.36 (KHTML, like Gecko) "
          f"Chrome/{ver} Safari/537.36")
    return {"ua": ua, "major": major, "ver": ver}

def apply_full_trace_removal(page):
    """Remove ALL automation traces (beyond just webdriver)."""
    page.add_init_script("""
    // Remove Playwright-specific traces
    ['__playwright', '__pw_manual', '_playwrightBinding',
     '__playwright__binding__', '__webdriver_evaluate',
     '__selenium_evaluate', '__webdriver_script_function',
     'cdc_adoQpoasnfa76pfcZLmcfl_Array', 'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
     'cdc_adoQpoasnfa76pfcZLmcfl_Symbol', 'domAutomation',
     'domAutomationController', '_selenium', 'calledSelenium'
    ].forEach(k => { try { delete window[k]; } catch(_) {} });

    // Fake chrome runtime (sites check for this)
    if (!window.chrome) {
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
    }

    // Permissions API (real browsers return 'denied' not 'prompt')
    const _origQuery = Permissions.prototype.query;
    Permissions.prototype.query = function(desc) {
        if (desc.name === 'notifications')
            return Promise.resolve({state: 'denied', onchange: null});
        return _origQuery.call(this, desc);
    };
    """)

def test_stealth():
    fp = get_test_fingerprint()
    print(f"\n{'='*50}")
    print(f"Testing stealth features")
    print(f"Chrome version: {fp['ver']}")
    print(f"UA: {fp['ua'][:80]}...")
    print(f"{'='*50}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=fp["ua"],
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "sec-ch-ua": f'"Google Chrome";v="{fp["major"]}", "Chromium";v="{fp["major"]}", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )
        page = context.new_page()

        # 1. Apply playwright-stealth (if available)
        if HAS_STEALTH:
            stealth_sync(page)
            print("[1] playwright-stealth applied: YES")
        else:
            print("[1] playwright-stealth applied: NO (not installed)")

        # 2. Apply full trace removal
        apply_full_trace_removal(page)
        print("[2] Full trace removal applied: YES")

        # 3. Test on bot detection site
        print("\n[3] Testing on bot.sannysoft.com...")
        try:
            page.goto("https://bot.sannysoft.com/", timeout=30000)
            page.wait_for_timeout(5000)

            # Check webdriver flag
            wd = page.evaluate("navigator.webdriver")
            print(f"    navigator.webdriver: {wd} (should be False/undefined)")

            # Check chrome runtime
            chrome = page.evaluate("typeof window.chrome")
            print(f"    window.chrome: {chrome} (should be 'object')")

            # Check user agent
            ua = page.evaluate("navigator.userAgent")
            print(f"    UA matches: {'Chrome/' + fp['ver'] in ua}")

            # Take screenshot
            page.screenshot(path="test_stealth_result.png")
            print(f"\n    Screenshot saved: test_stealth_result.png")
            print(f"    Check the page visually for green (pass) vs red (fail) indicators")

        except Exception as e:
            print(f"    Test site failed: {e}")

        print(f"\n{'='*50}")
        print("Test complete. Press Enter to close browser...")
        print(f"{'='*50}")
        input()
        browser.close()

if __name__ == "__main__":
    test_stealth()
