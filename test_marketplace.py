"""Test: Marketplace Automation (1 account, 1 listing with Gemini content).
Run: python test_marketplace.py

Reads:
  output/browser_accounts.txt  (uid|password|cookies)
  product.txt                  (basic product info from client)
  photos/                      (product images folder)

Needs: GEMINI_API_KEY environment variable or input at runtime.

Separate test - does NOT touch main tool.
"""
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright
from automation.browser_register import (
    _apply_fingerprint_spoof,
    _human_type,
    _human_pause,
    _human_click,
    _launch_browser,
)
from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN
from ui.display import print_lock

BASE = os.path.dirname(os.path.abspath(__file__))


def get_gemini_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    return input(f"{CYAN}Enter Gemini API Key: {WHITE}").strip()


def gemini_generate(product_info, api_key):
    """Use Gemini to generate unique title + description."""
    try:
        import google.generativeai as genai
    except ImportError:
        print(f"{YELLOW}Installing google-generativeai...{WHITE}")
        os.system(f"{sys.executable} -m pip install google-generativeai -q")
        import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"""You are a Facebook Marketplace listing expert. Given this product info:
{product_info}

Generate a compelling marketplace listing in this exact format:
TITLE: <catchy title under 60 chars>
PRICE: <suggested fair price with currency>
DESCRIPTION: <2-3 sentence engaging description>

Make it unique and human-sounding. Only output the 3 lines above."""

    resp = model.generate_content(prompt)
    text = resp.text.strip()
    title, price, desc = "", "", ""
    for line in text.split("\n"):
        l = line.strip()
        if l.upper().startswith("TITLE:"):
            title = l[6:].strip()
        elif l.upper().startswith("PRICE:"):
            price = l[6:].strip()
        elif l.upper().startswith("DESCRIPTION:"):
            desc = l[12:].strip()
    return title, price, desc


def fb_login(page, uid, password):
    """Login to Facebook with uid/email + password."""
    page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
    _human_pause(1.0, 2.0)
    try:
        page.get_by_label("Email or phone").fill(uid)
    except Exception:
        page.locator('input[name="email"]').fill(uid)
    _human_pause(0.5, 1.0)
    try:
        page.get_by_label("Password").fill(password)
    except Exception:
        page.locator('input[name="pass"]').fill(password)
    _human_pause(0.5, 1.0)
    try:
        page.get_by_role("button", name="Log in", exact=True).click()
    except Exception:
        page.keyboard.press("Enter")
    for _ in range(20):
        try:
            if "login" not in page.url or "checkpoint" in page.url:
                break
        except Exception:
            pass
        time.sleep(1.0)
    time.sleep(random.uniform(2.0, 3.0))
    return "checkpoint" not in page.url


def create_listing(page, title, price, description, photo_paths):
    """Create a marketplace listing."""
    page.goto("https://www.facebook.com/marketplace/create/item",
              wait_until="domcontentloaded", timeout=30000)
    _human_pause(2.0, 3.0)

    # Upload photos
    if photo_paths:
        try:
            page.locator('input[type="file"]').first.set_input_files(photo_paths[:5])
            with print_lock:
                print(f"{CYAN}[Marketplace] Photos uploaded{WHITE}")
        except Exception as e:
            with print_lock:
                print(f"{YELLOW}[Marketplace] Photo upload: {e}{WHITE}")
    _human_pause(1.5, 2.5)

    # Title
    try:
        _human_type(page, page.get_by_label("Title").first, title)
    except Exception as e:
        print(f"{RED}[Marketplace] Title failed: {e}{WHITE}")
        return False
    _human_pause(0.8, 1.5)

    # Price
    try:
        _human_type(page, page.get_by_label("Price").first, price)
    except Exception as e:
        print(f"{YELLOW}[Marketplace] Price: {e}{WHITE}")
    _human_pause(0.8, 1.5)

    # Description
    try:
        _human_type(page, page.get_by_label("Description").first, description)
    except Exception as e:
        print(f"{YELLOW}[Marketplace] Description: {e}{WHITE}")
    _human_pause(1.0, 2.0)

    # Publish
    try:
        _human_click(page, page.get_by_role("button", name="Publish").first)
        with print_lock:
            print(f"{GREEN}[Marketplace] Publish clicked{WHITE}")
    except Exception as e:
        print(f"{RED}[Marketplace] Publish failed: {e}{WHITE}")
        return False
    time.sleep(random.uniform(3.0, 5.0))
    return True


def main():
    print(f"{CYAN}=== Marketplace Automation TEST ==={WHITE}")

    acc_path = os.path.join(BASE, "output", "browser_accounts.txt")
    if not os.path.exists(acc_path):
        print(f"{RED}No accounts file{WHITE}")
        return
    with open(acc_path) as f:
        accounts = [l.strip() for l in f if l.strip()]
    if not accounts:
        print(f"{RED}No accounts{WHITE}")
        return

    prod_path = os.path.join(BASE, "product.txt")
    if not os.path.exists(prod_path):
        print(f"{RED}product.txt not found - write basic product info there{WHITE}")
        return
    with open(prod_path) as f:
        product_info = f.read().strip()

    photos_dir = os.path.join(BASE, "photos")
    photo_paths = []
    if os.path.isdir(photos_dir):
        photo_paths = [os.path.join(photos_dir, f) for f in os.listdir(photos_dir)
                       if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]

    print(f"{CYAN}Product info: {product_info[:80]}...{WHITE}")
    print(f"{CYAN}Photos: {len(photo_paths)}{WHITE}")

    # Gemini generates listing content
    api_key = get_gemini_key()
    if not api_key:
        print(f"{RED}No API key{WHITE}")
        return
    print(f"{CYAN}Asking Gemini for listing content...{WHITE}")
    title, price, desc = gemini_generate(product_info, api_key)
    print(f"{GREEN}Title: {title}{WHITE}")
    print(f"{GREEN}Price: {price}{WHITE}")
    print(f"{GREEN}Description: {desc[:100]}...{WHITE}")

    parts = accounts[0].split("|")
    uid, password = parts[0], parts[1]

    with sync_playwright() as p:
        _exe = os.path.expandvars(
            r"C:\Users\Rizvi Lion\AppData\Local\ms-playwright\chromium-1243\chrome-win\chrome.exe"
        )
        _launch_kwargs = dict(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        browser = _launch_browser(p, _launch_kwargs, _exe)

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

        try:
            if not fb_login(page, uid, password):
                print(f"{RED}[Marketplace] Login failed{WHITE}")
                return
            print(f"{GREEN}[Marketplace] Logged in: {uid}{WHITE}")

            if create_listing(page, title, price, desc, photo_paths):
                print(f"\n{GREEN}[Marketplace] TEST SUCCESS: Listing published{WHITE}")
            else:
                print(f"\n{RED}[Marketplace] TEST FAILED{WHITE}")
        except Exception as e:
            print(f"{RED}[Marketplace] Error: {e}{WHITE}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
