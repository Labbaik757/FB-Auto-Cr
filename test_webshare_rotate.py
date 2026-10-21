"""
TEST FILE - Webshare Rotating Proxy for Mode 4 (Outlook)
====================================================================
Webshare's official rotating setup (from their site's code):
    proxy = "http://USERNAME-rotate:PASSWORD@p.webshare.io:80/"
    - A single endpoint, no list
    - "-rotate" in the username is required
    - Every new connection gets a fresh IP from Webshare

Put your details in proxies.txt as ONE line:
    http://YOURUSER-rotate:YOURPASS@p.webshare.io:80

Run:
    python test_webshare_rotate.py           # offline: format/rotate-detect test
    python test_webshare_rotate.py --live    # live: 3 IP checks, a different IP each time

When the live test shows 3 different IPs, rotation works.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.proxy_manager import (
    parse_proxy,
    build_proxy_data,
    format_proxy_for_playwright,
    is_rotating_proxy,
    load_proxies_from_file,
)

PASS = 0
FAIL = 0

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name} {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def test_official_format():
    print("\n== 1. Webshare official format ==")
    # The format Webshare gives on their site (Python example)
    raw = "http://myuser-rotate:mypass@p.webshare.io:80/"
    p = parse_proxy(raw)
    check("parse server", p and p["http"] == "http://p.webshare.io:80", f"-> {p}")
    check("username me -rotate", p and p.get("username") == "myuser-rotate")
    check("password", p and p.get("password") == "mypass")
    check("is_rotating detect", is_rotating_proxy(p) is True)

    # Webshare without -rotate = NOT rotating (static/direct)
    p2 = parse_proxy("http://myuser:mypass@p.webshare.io:80/")
    check("bina -rotate = not rotating", is_rotating_proxy(p2) is False)

    # Webshare's official requests code builds this same dict:
    req_format = {
        "http": "http://myuser-rotate:mypass@p.webshare.io:80/",
        "https": "http://myuser-rotate:mypass@p.webshare.io:80/",
    }
    print(f"  Webshare requests code: {req_format}")

    # Playwright format (for Mode 4) - server separate, user/pass separate fields
    fake_data = {
        "proxy": p, "country": "United States", "country_code": "US",
        "locale": "en_US", "language": "en-US",
        "timezone": "America/New_York", "ip_timezone": "America/New_York",
        "rotating": True,
    }
    pw = format_proxy_for_playwright(fake_data)
    check("playwright server", pw and pw["server"] == "http://p.webshare.io:80", f"-> {pw}")
    check("playwright username", pw and pw["username"] == "myuser-rotate")
    check("playwright password", pw and pw["password"] == "mypass")


def test_build_skips_geo():
    print("\n== 2. Rotating proxy par geo-check skip ==")
    print("  (On rotating proxies an ip-api check is useless - the browser gets a different IP)")
    p = parse_proxy("http://myuser-rotate:mypass@p.webshare.io:80/")
    data = build_proxy_data(p)
    check("rotating flag set", data.get("rotating") is True)
    check("proxy preserved", data["proxy"]["http"] == "http://p.webshare.io:80")


def load_my_webshare():
    proxies = load_proxies_from_file(verbose=True)
    ws = [p for p in proxies if p.get("rotating")]
    return ws


def test_live():
    print("\n== 3. LIVE test - 3 connections, 3 different IPs expected ==")
    ws = load_my_webshare()
    if not ws:
        print("  [SKIP] proxies.txt me Webshare rotating line nahi mili")
        print("  Daalo: http://YOURUSER-rotate:YOURPASS@p.webshare.io:80")
        return
    data = ws[0]
    pw_proxy = format_proxy_for_playwright(data)
    print(f"  Endpoint: {pw_proxy['server']} user={pw_proxy.get('username')}")

    # First test with requests (Webshare's own official method)
    try:
        import requests
        proxy_url = f"http://{pw_proxy['username']}:{pw_proxy['password']}@p.webshare.io:80"
        ips = []
        for i in range(3):
            r = requests.get("https://ipv4.webshare.io/", proxies={"http": proxy_url, "https": proxy_url}, timeout=20)
            ip = r.text.strip()
            ips.append(ip)
            print(f"    Request {i+1}: IP = {ip}")
        check("got 3 IPs", len(ips) == 3)
        check("IPs are different (rotation is working)", len(set(ips)) > 1, f"-> {ips}")
    except Exception as e:
        check("requests live test", False, f"{e}")

    # Then test with Playwright (what Mode 4 actually uses)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            browser_ips = []
            for i in range(3):
                ctx = browser.new_context(proxy=pw_proxy)
                page = ctx.new_page()
                page.goto("https://ipv4.webshare.io/", timeout=25000)
                ip = page.inner_text("body").strip()
                browser_ips.append(ip)
                print(f"    Browser context {i+1}: IP = {ip}")
                ctx.close()
            browser.close()
            check("browser IPs are different", len(set(browser_ips)) > 1, f"-> {browser_ips}")
    except ImportError:
        print("  [SKIP] Playwright not installed - browser part skipped")
    except Exception as e:
        check("playwright live test", False, f"{e}")


if __name__ == "__main__":
    print("=" * 62)
    print(" Webshare Rotating Proxy - Mode 4 TEST (alag file)")
    print("=" * 62)
    test_official_format()
    test_build_skips_geo()
    if "--live" in sys.argv:
        test_live()
    else:
        print("\n  For live: first put your Webshare line in proxies.txt, then:")
        print("  python test_webshare_rotate.py --live")
    print(f"\n{'='*62}\n RESULT: {PASS} passed, {FAIL} failed\n{'='*62}")
    sys.exit(1 if FAIL else 0)
