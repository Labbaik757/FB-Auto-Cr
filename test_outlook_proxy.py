"""
TEST FILE - Mode 4 (Outlook) Proxy - Alag test, permanent nahi
=============================================================
Run:
    python test_outlook_proxy.py          # offline tests (parsing, rotation, format)
    python test_outlook_proxy.py --live   # live test: proxies.txt wali har proxy se
                                          # browser khol ke IP check karega

Jab ye test PASS ho jaye, tabhi ye changes GitHub project me permanent honge.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.proxy_manager import (
    parse_proxy,
    format_proxy_for_playwright,
    load_proxies_from_file,
    create_proxy_cycle,
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


def test_parse():
    print("\n== 1. Proxy format parsing ==")
    cases = [
        ("1.2.3.4:8080", "http://1.2.3.4:8080", None, None),
        ("1.2.3.4:8080:user1:pass1", "http://1.2.3.4:8080", "user1", "pass1"),
        ("http://1.2.3.4:8080", "http://1.2.3.4:8080", None, None),
        ("http://user1:pass1@1.2.3.4:8080", "http://1.2.3.4:8080", "user1", "pass1"),
        ("socks5://1.2.3.4:1080", "socks5://1.2.3.4:1080", None, None),
        ("socks5://user1:pass1@1.2.3.4:1080", "socks5://1.2.3.4:1080", "user1", "pass1"),
    ]
    for raw, exp_url, exp_u, exp_p in cases:
        p = parse_proxy(raw)
        ok = p and p["http"] == exp_url and p.get("username") == exp_u and p.get("password") == exp_p
        check(raw, bool(ok), f"-> {p}")

    check("invalid should fail", parse_proxy("not-a-proxy") is None)
    check("bad port should fail", parse_proxy("1.2.3.4:abc") is None)


def test_playwright_format():
    print("\n== 2. Playwright format conversion ==")
    # Fake proxy_data, jaisa build_proxy_data banata hai (network call nahi)
    fake = {
        "proxy": {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080",
                  "username": "user1", "password": "pass1"},
        "country": "United States", "country_code": "US",
        "locale": "en_US", "language": "en-US",
        "timezone": "America/New_York", "ip_timezone": "America/New_York",
    }
    pw = format_proxy_for_playwright(fake)
    check("server", pw and pw.get("server") == "http://1.2.3.4:8080", f"-> {pw}")
    check("username", pw and pw.get("username") == "user1")
    check("password", pw and pw.get("password") == "pass1")
    check("no proxy -> None", format_proxy_for_playwright(None) is None)
    check("empty proxy -> None", format_proxy_for_playwright({"proxy": None}) is None)

    fake2 = dict(fake)
    fake2["proxy"] = {"http": "socks5://5.6.7.8:1080", "https": "socks5://5.6.7.8:1080",
                      "username": None, "password": None}
    pw2 = format_proxy_for_playwright(fake2)
    check("socks5 no-auth", pw2 == {"server": "socks5://5.6.7.8:1080"}, f"-> {pw2}")


def test_file_and_rotation():
    print("\n== 3. proxies.txt loading + rotation ==")
    proxies = load_proxies_from_file(verbose=True)
    if not proxies:
        print("  [SKIP] proxies.txt me koi real proxy nahi hai - dummy se rotation test")
        # Dummy proxy_data list bana ke rotation test
        dummies = []
        for i in range(3):
            dummies.append({
                "proxy": {"http": f"http://10.0.0.{i+1}:8080", "https": f"http://10.0.0.{i+1}:8080",
                          "username": None, "password": None},
                "country": "United States", "country_code": "US",
                "locale": "en_US", "language": "en-US",
                "timezone": "America/New_York", "ip_timezone": "America/New_York",
            })
        cycle = create_proxy_cycle(dummies)
        seq = [next(cycle)["proxy"]["http"] for _ in range(5)]
        expected = ["http://10.0.0.1:8080", "http://10.0.0.2:8080", "http://10.0.0.3:8080",
                    "http://10.0.0.1:8080", "http://10.0.0.2:8080"]
        check("round-robin rotation", seq == expected, f"-> {seq}")
        return []
    print(f"  Loaded {len(proxies)} proxies from file")
    for p in proxies:
        pw = format_proxy_for_playwright(p)
        print(f"    - {pw['server']} | {p.get('country')} | {p.get('ip_timezone')} | auth={'yes' if pw.get('username') else 'no'}")
        check(f"playwright format {pw['server']}", pw.get("server") is not None)
    cycle = create_proxy_cycle(proxies)
    first = next(cycle)
    for _ in range(len(proxies) - 1):
        next(cycle)
    again = next(cycle)
    check("rotation wraps to first", first["proxy"] == again["proxy"])
    return proxies


def test_live(proxies):
    print("\n== 4. LIVE test - har proxy se asal IP check ==")
    if not proxies:
        print("  [SKIP] proxies.txt me real proxy daalo, phir --live chalao")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [SKIP] Playwright installed nahi: pip install playwright && playwright install chromium")
        return
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for i, pdata in enumerate(proxies, 1):
            pw_proxy = format_proxy_for_playwright(pdata)
            print(f"\n  Proxy {i}: {pw_proxy['server']} (expected country: {pdata.get('country')})")
            try:
                ctx = browser.new_context(proxy=pw_proxy)
                page = ctx.new_page()
                page.goto("http://ip-api.com/json/", timeout=20000)
                body = page.inner_text("body")
                print(f"    Response: {body[:200]}")
                check(f"proxy {i} live IP response", "country" in body or "query" in body)
                ctx.close()
            except Exception as e:
                check(f"proxy {i} live", False, f"error: {e}")
        browser.close()


if __name__ == "__main__":
    print("=" * 60)
    print(" Mode 4 Outlook Proxy - TEST (alag file, permanent nahi)")
    print("=" * 60)
    test_parse()
    test_playwright_format()
    proxies = test_file_and_rotation()
    if "--live" in sys.argv:
        test_live(proxies)
    else:
        print("\n  Live test ke liye: python test_outlook_proxy.py --live")
    print(f"\n{'='*60}\n RESULT: {PASS} passed, {FAIL} failed\n{'='*60}")
    sys.exit(1 if FAIL else 0)
