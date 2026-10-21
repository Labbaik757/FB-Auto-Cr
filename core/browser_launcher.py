"""
Shared browser launcher with 3 options:
1. Chromium (default Playwright)
2. Real Chrome (channel="chrome")
3. CloakBrowser (if installed, else falls back to Chromium)

Used by all browser-based modes.
"""
import os


def _check_cloakbrowser():
    """Check if cloakbrowser is installed."""
    try:
        import cloakbrowser
        return True
    except ImportError:
        return False


def get_browser_choice():
    """Ask user which browser to use. Returns 'chromium', 'chrome', or 'cloak'."""
    print("\n" + "="*50)
    print("Select browser:")
    print("  [1] Chromium (default, fast)")
    print("  [2] Real Chrome (looks more real)")
    cloak_ok = _check_cloakbrowser()
    if cloak_ok:
        print("  [3] CloakBrowser (stealth, free tier)")
    else:
        print("  [3] CloakBrowser (not installed - pip install cloakbrowser)")
    print("="*50)
    try:
        choice = input("Choice [1/2/3] (default 1): ").strip()
    except Exception:
        choice = "1"
    if choice == "2":
        return "chrome"
    elif choice == "3" and cloak_ok:
        return "cloak"
    return "chromium"


def launch_browser(p, browser_type="chromium", headless=False):
    """
    Launch browser based on type.
    Returns (browser, is_cloak) tuple.
    """
    args = ["--disable-blink-features=AutomationControlled"]

    if browser_type == "cloak":
        try:
            from cloakbrowser import launch as cloak_launch
            browser = cloak_launch(headless=headless)
            print("[Browser] CloakBrowser launched")
            return browser, True
        except Exception as e:
            print(f"[Browser] CloakBrowser failed ({e}), falling back to Chromium")
            browser_type = "chromium"

    if browser_type == "chrome":
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless, args=args)
            print("[Browser] Real Chrome launched")
            return browser, False
        except Exception as e:
            print(f"[Browser] Real Chrome failed ({e}), falling back to Chromium")
            browser_type = "chromium"

    # Default: Chromium
    _exe = os.path.expandvars(
        r"C:\Users\Rizvi Lion\AppData\Local\ms-playwright\chromium-1243\chrome-win\chrome.exe"
    )
    kwargs = dict(headless=headless, args=args)
    if os.path.exists(_exe):
        kwargs["executable_path"] = _exe
    browser = p.chromium.launch(**kwargs)
    print("[Browser] Chromium launched")
    return browser, False
