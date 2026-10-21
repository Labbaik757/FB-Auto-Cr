import os
import glob as _glob
import time
import itertools
from concurrent.futures import ThreadPoolExecutor
import requests
from urllib.parse import urlparse
from ui.colors import GREEN, RED, WHITE, EKL
from core.settings_manager import load_settings
from core.locale_data import get_locale, get_timezone, get_language

FALLBACK_IP_INFO = {"country": "United States", "countryCode": "US", "timezone": "America/New_York"}


# Parse proxy string into structured dict (supports ip:port, ip:port:user:pass, and URL formats)
def parse_proxy(proxy_str):
    proxy_str = proxy_str.strip()
    username = None
    password = None

    if "://" not in proxy_str:
        parts = proxy_str.split(":")
        if len(parts) == 2:
            ip, port = parts
            if not port.isdigit():
                return None
            proxy_url = f"http://{ip}:{port}"
        elif len(parts) >= 4:
            ip = parts[0]
            port = parts[1]
            if not port.isdigit():
                return None
            username = parts[2]
            password = ":".join(parts[3:])
            proxy_url = f"http://{ip}:{port}"
        else:
            return None
    else:
        try:
            parsed = urlparse(proxy_str)
            username = parsed.username
            password = parsed.password
            netloc = parsed.netloc
            if '@' in netloc:
                netloc = netloc.split('@')[-1]
            proxy_url = f"{parsed.scheme or 'http'}://{netloc}"
        except Exception:
            return None

    return {
        "http": proxy_url,
        "https": proxy_url,
        "username": username,
        "password": password
    }


# Fetch geolocation info for a proxy using ip-api.com
def get_ip_info(proxies=None, retries=1):
    for attempt in range(retries + 1):
        try:
            r = requests.get("http://ip-api.com/json/", proxies=proxies, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return {
                    "country": data.get("country", "Unknown"),
                    "countryCode": data.get("countryCode", "US"),
                    "timezone": data.get("timezone", "Unknown")
                }
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1)
    return None


# Check if a proxy_dict / proxy_data is a Webshare rotating endpoint
# Webshare rotating: server p.webshare.io + username ends with / contains "-rotate"
# Example: http://myuser-rotate:mypass@p.webshare.io:80/
# Server-side rotation - every new connection gets a new IP, no list needed.
def is_rotating_proxy(proxy_dict_or_data):
    if not proxy_dict_or_data:
        return False
    d = proxy_dict_or_data.get("proxy") if "proxy" in proxy_dict_or_data else proxy_dict_or_data
    if not isinstance(d, dict):
        return False
    user = (d.get("username") or "")
    server = (d.get("http") or d.get("https") or "")
    return "-rotate" in user and "webshare" in server


# Build complete proxy data dict with locale, timezone, and language info
def build_proxy_data(proxy_dict):
    req_proxies = None
    rotating = is_rotating_proxy(proxy_dict)
    if proxy_dict:
        username = proxy_dict.get("username")
        password = proxy_dict.get("password")
        raw_url = proxy_dict.get("http", "")
        if username and password:
            if "://" in raw_url:
                proto, host = raw_url.split("://", 1)
                auth_url = f"{proto}://{username}:{password}@{host}"
            else:
                auth_url = f"http://{username}:{password}@{raw_url}"
            req_proxies = {"http": auth_url, "https": auth_url}
        else:
            req_proxies = proxy_dict

    if rotating:
        # Rotating endpoint: a geo-check here would burn one rotation and the
        # IP it returns is NOT the IP the browser session will get next.
        # So skip ip-api, use US fallback, and mark rotating=True.
        # Real country/timezone will differ per session (Webshare pool).
        info = FALLBACK_IP_INFO
    else:
        info = get_ip_info(req_proxies)
        if info is None:
            print(f"{RED} Warning: Could not determine location for proxy. Using default US settings.")
            info = FALLBACK_IP_INFO
    cc = info["countryCode"]
    return {
        "proxy": proxy_dict,
        "country": info["country"],
        "country_code": cc,
        "locale": get_locale(cc),
        "timezone": get_timezone(cc),
        "language": get_language(cc),
        "ip_timezone": info["timezone"],
        "rotating": rotating,
    }


# Parse and validate a single proxy input string
def _input_single_proxy_internal(proxy_str, proxy_list):
    parsed = parse_proxy(proxy_str)
    if parsed:
        data = build_proxy_data(parsed)
        proxy_list.append(data)
    else:
        print(f"{RED} Invalid proxy format!")


# Prompt user for multiple proxy inputs (max 40)
def _input_multiple_proxies_internal(prompt_label, proxy_list):
    try:
        cnt_str = input(f" {GREEN}[{RED}●{GREEN}] How many proxies? (Max 40) {EKL} ").strip()
        if not cnt_str or not cnt_str.isdigit():
            print(f"{RED} Invalid number!")
            return
        cnt = int(cnt_str)
        if cnt > 40:
            print(f"{RED} Maximum 40 proxies allowed! You entered {cnt}.")
            return
        if cnt < 1:
            print(f"{RED} Invalid number!")
            return
        for i in range(cnt):
            while True:
                p_str = input(f" {WHITE}[{RED}●{WHITE}] Enter {prompt_label} [{i+1}/{cnt}] {EKL} ").strip()
                if not p_str:
                    continue
                parsed = parse_proxy(p_str)
                if parsed:
                    data = build_proxy_data(parsed)
                    proxy_list.append(data)
                    break
                else:
                    print(f"{RED} Invalid proxy format!")
    except KeyboardInterrupt:
        raise
    except Exception:
        print(f"{RED} Invalid input!")


# Format proxy config display label for the UI
def _format_proxy_config_label(proxy_list, source="User"):
    if not proxy_list:
        return "Direct"
    if len(proxy_list) == 1:
        p = proxy_list[0]
        if source == "Settings":
            return f"{p['country']} (Settings)"
        else:
            return f"{p['country']} (IP: {p['ip_timezone']})"
    countries = set(p['country'] for p in proxy_list)
    suffix = " (Settings)" if source == "Settings" else ""
    return f"{len(proxy_list)} Proxies ({len(countries)} Countries){suffix}"


# Main proxy input handler - loads from settings or prompts user
def get_proxy_list(config_state=None, render_callback=None):
    settings = load_settings()
    proxy_cfg = settings.get("proxy_settings", {})
    ask_proxy = proxy_cfg.get("ask_for_proxy", True)
    def_proxy = proxy_cfg.get("default_proxy", "")
    prompt_label = "Proxy"
    config_key = "proxy"

    proxy_list = []

    # Load proxies from settings if configured
    if def_proxy:
        parsed_proxies = []
        if isinstance(def_proxy, list):
            if len(def_proxy) > 40:
                print(f"{RED} Warning: Maximum 40 proxies allowed in settings. Using first 40.")
                def_proxy = def_proxy[:40]
            for p in def_proxy:
                parsed = parse_proxy(p)
                if parsed:
                    parsed_proxies.append(parsed)
                else:
                    print(f"{RED} Warning: Skipping invalid proxy in settings: {p}")
        elif def_proxy.strip():
            parsed = parse_proxy(def_proxy)
            if parsed:
                parsed_proxies.append(parsed)
            else:
                print(f"{RED} Warning: Skipping invalid proxy in settings: {def_proxy}")
        if parsed_proxies:
            with ThreadPoolExecutor(max_workers=min(len(parsed_proxies), 5)) as executor:
                proxy_list.extend(executor.map(build_proxy_data, parsed_proxies))

    # proxies.txt auto-load (highest priority after settings) - if file has
    # proxies, use them and skip the manual prompt entirely.
    if not proxy_list:
        try:
            file_proxies = load_proxies_from_file(verbose=True)
            if file_proxies:
                proxy_list.extend(file_proxies)
                if config_state is not None:
                    countries = set(p['country'] for p in proxy_list)
                    config_state[config_key] = f"{len(proxy_list)} Proxies ({len(countries)} Countries) (proxies.txt)"
                return proxy_list
        except Exception:
            pass

    if not ask_proxy:
        if config_state is not None:
            config_state[config_key] = _format_proxy_config_label(proxy_list, "Settings")
        return proxy_list

    if render_callback:
        render_callback()

    proxy_input = input(f" {GREEN}[{RED}●{GREEN}] Enter {prompt_label} (or 'y' for multiple) [Enter to Skip] {EKL} ").strip()

    if proxy_input.lower() == 'y':
        _input_multiple_proxies_internal(prompt_label, proxy_list)
    elif proxy_input:
        _input_single_proxy_internal(proxy_input, proxy_list)

    if config_state is not None:
        if not proxy_list:
            no_proxy_data = get_no_proxy_data()
            config_state[config_key] = f"Direct (IP: {no_proxy_data['country']})"
        else:
            config_state[config_key] = _format_proxy_config_label(proxy_list, "User")

    return proxy_list


# Create infinite cycling iterator for round-robin proxy rotation
def create_proxy_cycle(proxy_list):
    if proxy_list:
        return itertools.cycle(proxy_list)
    return None


# Get locale data for direct connection (no proxy)
def get_no_proxy_data():
    info = get_ip_info(None)
    if info is None:
        info = FALLBACK_IP_INFO
    cc = info["countryCode"]
    return {
        "proxy": None,
        "country": info["country"],
        "country_code": cc,
        "locale": get_locale(cc),
        "timezone": get_timezone(cc),
        "language": get_language(cc),
        "ip_timezone": info["timezone"]
    }


# --- proxies.txt support (Mode 4 / Outlook + all modes) ---

def _proxy_search_dirs():
    dirs = []
    dirs.append(os.path.abspath("."))
    # Project root = parent of core/ (works even if run from another folder)
    try:
        dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except Exception:
        pass
    try:
        from core.path_manager import get_base_storage_dir
        dirs.append(get_base_storage_dir())
    except Exception:
        pass
    home = os.path.expanduser("~")
    dirs.append(home)
    dirs.append(os.path.join(home, "Downloads"))
    dirs.append(os.path.join(home, "Desktop"))
    dirs.append(os.path.join(home, "Documents"))
    # de-dupe, keep order, only existing dirs
    seen = set()
    out = []
    for d in dirs:
        key = os.path.normcase(os.path.abspath(d)) if d else ""
        if key and key not in seen and os.path.isdir(d):
            seen.add(key)
            out.append(d)
    return out


def _read_proxy_lines(path):
    """Read a file robustly (utf-8 / utf-16 / BOM) and return non-comment lines."""
    for enc in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            with open(path, encoding=enc) as f:
                text = f.read()
            if "\x00" in text:
                continue
            lines = []
            for l in text.splitlines():
                l = l.strip().strip("\ufeff")
                if l and not l.startswith("#"):
                    lines.append(l)
            return lines
        except Exception:
            continue
    return []


def _proxy_file_candidates(filepath=None):
    """Auto-find proxy file: koi naam / koi jagah fix nahi.
    Priority: exact proxies.txt (incl. proxies.txt.txt galti) pehle, phir
    kisi bhi *proxies* / *proxy* / Webshare* naam wali .txt file upar wali
    folders me. proxies.example.txt hamesha skip (wo sirf template hai).
    """
    if filepath:
        return [filepath]
    cands = []
    for d in _proxy_search_dirs():
        # 1) exact names first
        for name in ("proxies.txt", "proxies.txt.txt", "proxy.txt", "Proxy.txt"):
            cands.append(os.path.join(d, name))
        # 2) any similar name in that folder
        try:
            for path in _glob.glob(os.path.join(d, "*.txt")):
                base = os.path.basename(path).lower()
                if base == "proxies.example.txt":
                    continue
                if "prox" in base or "webshare" in base:
                    cands.append(path)
        except Exception:
            pass
    # de-dupe, keep order
    seen = set()
    out = []
    for c in cands:
        key = os.path.normcase(os.path.abspath(c))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def load_proxies_from_file(filepath=None, verbose=True):
    """Auto-load proxies from file - file jahan bhi ho, naam proxies jaisa
    koi bhi ho (proxies.txt, Webshare_10_proxies.txt, Downloads me bhi chalegi).
    Jis file me asal valid proxy lines hongi, wohi use hogi. Template /
    comment-only file khud skip ho jayegi.
    """
    searched = _proxy_file_candidates(filepath)
    for cand in searched:
        if not os.path.exists(cand):
            continue
        lines = _read_proxy_lines(cand)
        if not lines:
            continue  # empty / sirf comments - agli file dekho
        parsed_list = []
        for line in lines:
            parsed = parse_proxy(line)
            if parsed:
                parsed_list.append(parsed)
        if not parsed_list:
            continue  # is file me koi valid proxy nahi - agli dekho
        if verbose:
            print(f"{GREEN} Loading {len(parsed_list)} proxies from {cand}")
        with ThreadPoolExecutor(max_workers=min(len(parsed_list), 5)) as executor:
            return list(executor.map(build_proxy_data, parsed_list))
    if verbose:
        dirs = ", ".join(_proxy_search_dirs())
        print(f"{RED} Proxy file nahi mili. In folders me dhunda: {dirs}")
        print(f"{RED} File ka naam proxies jaisa rakho (misal: proxies.txt ya Webshare_10_proxies.txt) aur upar wali kisi folder me rakho.")
    return []


def format_proxy_for_playwright(proxy_data):
    """Convert proxy_data (from build_proxy_data / get_proxy_list) into
    Playwright format: {"server": "http://ip:port", "username": ..., "password": ...}
    Returns None for direct connection.
    Playwright does NOT support socks5 with auth - it will pass through and
    Playwright/Chromium will reject it; http/https proxies are recommended.
    """
    if not proxy_data:
        return None
    proxy_dict = proxy_data.get("proxy")
    if not proxy_dict:
        return None
    if isinstance(proxy_dict, dict):
        server = proxy_dict.get("http") or proxy_dict.get("https") or ""
        if not server:
            return None
        result = {"server": server}
        if proxy_dict.get("username"):
            result["username"] = proxy_dict["username"]
        if proxy_dict.get("password"):
            result["password"] = proxy_dict["password"]
        return result
    # plain string fallback
    return {"server": str(proxy_dict)}


# Convert proxy_data dict into requests-compatible proxy format with auth
def format_proxy_for_requests(proxy_data):
    if not proxy_data:
        return None
    proxy_url = proxy_data.get("proxy")
    if not proxy_url:
        return None
    if isinstance(proxy_url, dict):
        username = proxy_url.get("username")
        password = proxy_url.get("password")
        raw_url = proxy_url.get("http", "")
        if username and password:
            from urllib.parse import quote
            safe_user = quote(username, safe="")
            safe_pass = quote(password, safe="")
            if "://" in raw_url:
                proto, host = raw_url.split("://", 1)
                auth_url = f"{proto}://{safe_user}:{safe_pass}@{host}"
            else:
                auth_url = f"http://{safe_user}:{safe_pass}@{raw_url}"
            return {"http": auth_url, "https": auth_url}
        return {"http": raw_url, "https": proxy_url.get("https", raw_url)}
    return {"http": proxy_url, "https": proxy_url}
