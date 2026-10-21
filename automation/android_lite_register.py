"""
FB Auto Create -> Android Setup: Facebook account creation inside
the Facebook Lite ANDROID app (package com.facebook.lite) on an
emulator or a real Android phone connected over ADB. Selected from
inside Mode 2 (FB Auto Create) in main.py - the mode's original
Browser Setup stays exactly as it was; this is its separate part.

This is a NEW, self-contained module (added 2026-10-21). It does not
import, copy, or modify the Playwright browser code in any way - it
drives the Lite app purely with ADB commands + Android's built-in
uiautomator UI dumps, so it needs NO extra pip packages (Faker is
already a project dependency and is used for identities, like the
other modes).

Works ONLY with Facebook Lite - the regular Facebook app and the
mobile website are intentionally not supported here.

Flow per account:
    launch Lite (fresh app data) -> Create new account -> Name ->
    Date of birth -> Gender -> Email or Mobile number -> Password ->
    Sign Up -> (confirmation code / dialogs handled with the user) ->
    account saved to android_lite_accounts.txt
"""

import os
import re
import time
import random
import subprocess
import xml.etree.ElementTree as ET

from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN, EKL
from ui.display import print_lock

try:
    from faker import Faker
    _HAS_FAKER = True
except Exception:
    _HAS_FAKER = False

LITE_PACKAGE = "com.facebook.lite"

# ----------------------------------------------------------------------
# On-screen texts this module looks for in Facebook Lite (English UI).
# If Lite changes its wording in a future version, THIS is the only
# block that needs updating - everything below reads from here.
# ----------------------------------------------------------------------
# Facebook Lite ke DIFFERENT versions mukhtalif lafz istemal karte hain
# (kabhi "Create New Account", kabhi "Create new account", kabhi steps ki
# tartib bhi alag). Is liye har step ke saare mashhoor variants yahan hain,
# aur neeche ka flow tartib par nahi, screen par maujood khano par chalta
# hai - taake jis version par account banna mumkin ho, ban jaye.
TEXTS = {
    "create_account": ["Create new account", "Create New Account",
                       "Create account", "Create Account", "Join Facebook",
                       "Sign up for Facebook", "Get started", "Get Started",
                       "Sign Up", "Sign up"],
    "next": ["Next", "NEXT", "Continue", "CONTINUE"],
    "signup_with_email": ["Sign up with your email", "Use your email address",
                          "Sign up with email address", "Use email address",
                          "Use your email", "Sign up with email",
                          "Use email instead", "Email address"],
    "signup_button": ["Sign Up", "Sign up", "SIGN UP", "Create account",
                      "Create Account", "Register", "Join"],
    "confirm": ["Confirm", "Continue", "OK", "Submit", "Verify"],
    "dismiss_dialog": ["Not now", "Not Now", "NOT NOW", "Skip", "SKIP",
                       "Later", "No thanks", "No, thanks", "Cancel", "Deny",
                       "Don't allow", "Maybe later"],
    "gender": {"Male": ["Male", "MALE"], "Female": ["Female", "FEMALE"]},
    "gender_markers": ["Male", "Female", "What's your gender",
                       "Select your gender"],
    "dob_markers": ["date of birth", "Date of birth", "birthday",
                    "Birthday", "Birth"],
    "code_prompt": ["confirmation code", "Confirmation code",
                    "Enter the code", "enter the code we sent",
                    "Confirm your account", "Enter code",
                    "6-digit code", "verification code"],
    "feed_markers": ["What's on your mind", "News Feed", "Watch",
                     "Notifications", "Menu", "Find friends"],
    "blocked": ["We need to confirm your identity",
                "account has been disabled", "unusual activity",
                "temporarily blocked", "Confirm your identity"],
}

# Names that must never be used for generated identities (project-wide rule)
_BLOCKED_NAMES = {"king", "queen", "love", "prince", "princess", "angel",
                  "devil", "baby", "sweet", "cute", "star", "moon", "dark",
                  "dragon", "tiger", "lion", "wolf", "boss", "admin", "test",
                  "demo", "user", "facebook", "fb", "meta", "official",
                  "real", "fake"}
_MALE_FIRST = {"james", "john", "robert", "michael", "william", "david",
               "joseph", "daniel", "matthew", "andrew", "ryan", "kevin",
               "jason", "brian", "mark", "paul", "george", "henry", "jack",
               "oliver", "leo", "sam", "ben", "thomas", "liam", "noah",
               "ethan", "jacob", "lucas", "mason"}
_FEMALE_FIRST = {"mary", "emma", "sophia", "olivia", "isabella", "mia",
                 "ava", "lily", "emily", "sarah", "jessica", "anna", "lisa",
                 "kate", "jennifer", "rachel", "laura", "julia", "hannah",
                 "amelia", "chloe", "grace", "ella", "ruby", "zoe", "lucy",
                 "eva", "nora", "ivy", "aria", "sofia"}


def _pause(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))


# ----------------------------------------------------------------------
# ADB plumbing
# ----------------------------------------------------------------------
def _find_adb():
    """Locate the adb executable (PATH, then common Android SDK spots)."""
    import shutil
    found = shutil.which("adb")
    if found:
        return found
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Android", "Sdk", "platform-tools", "adb.exe"),
        os.path.join(home, "Android", "Sdk", "platform-tools", "adb"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk",
                     "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools",
                     "adb.exe"),
        os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools",
                     "adb"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _adb(adb, serial, *args, timeout=40):
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)


def _shell(adb, serial, command, timeout=40):
    return _adb(adb, serial, "shell", command, timeout=timeout)


def _list_devices(adb):
    try:
        out = _adb(adb, None, "devices", timeout=20).stdout
    except Exception:
        return []
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


# ----------------------------------------------------------------------
# UI inspection (uiautomator dump -> node list)
# ----------------------------------------------------------------------
def _dump_nodes(adb, serial):
    """Return the current screen as a flat list of UI node dicts."""
    try:
        _shell(adb, serial, "uiautomator dump /sdcard/_lite_ui.xml",
               timeout=25)
        raw = _adb(adb, serial, "exec-out", "cat", "/sdcard/_lite_ui.xml",
                   timeout=25).stdout
        root = ET.fromstring(raw)
    except Exception:
        return []
    nodes = []
    for elem in root.iter("node"):
        a = elem.attrib
        nodes.append({
            "text": a.get("text", "") or "",
            "desc": a.get("content-desc", "") or "",
            "rid": a.get("resource-id", "") or "",
            "cls": a.get("class", "") or "",
            "bounds": a.get("bounds", "") or "",
            "clickable": a.get("clickable") == "true",
            "password": a.get("password") == "true",
        })
    return nodes


def _center(bounds):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(v) for v in m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _tap(adb, serial, node):
    pos = _center(node["bounds"])
    if not pos:
        return False
    _shell(adb, serial, f"input tap {pos[0]} {pos[1]}", timeout=20)
    return True


def _find(nodes, texts=None, cls_contains=None):
    """First node whose text/desc matches one of `texts` (exact first,
    then substring), optionally restricted by class name."""
    pool = nodes
    if cls_contains:
        pool = [n for n in pool if cls_contains in n["cls"]]
    if texts:
        for want in texts:
            for n in pool:
                if n["text"] == want or n["desc"] == want:
                    return n
        for want in texts:
            for n in pool:
                if want and (want in n["text"] or want in n["desc"]):
                    return n
        return None
    return pool[0] if pool else None


def _screen_has(nodes, phrases):
    blob = " ".join(n["text"] + " " + n["desc"] for n in nodes)
    return any(p in blob for p in phrases)


def _wait_screen(adb, serial, phrases, timeout=25):
    """Poll the UI until any phrase is visible; return the node list."""
    end = time.time() + timeout
    nodes = []
    while time.time() < end:
        nodes = _dump_nodes(adb, serial)
        if _screen_has(nodes, phrases):
            return nodes
        time.sleep(1.5)
    return nodes


def _type_text(adb, serial, text):
    """Type text with the on-screen keyboard via adb input.
    Spaces become %s; shell-special chars are backslash-escaped."""
    safe = []
    for ch in str(text):
        if ch == " ":
            safe.append("%s")
        elif ch in '\\$&;|<>()`"\'':
            safe.append("\\" + ch)
        elif ch == "%":
            safe.append("\\%")
        else:
            safe.append(ch)
    _shell(adb, serial, "input text " + "".join(safe), timeout=30)


def _fill_field(adb, serial, node, value):
    """Tap an EditText, clear anything in it, type the value."""
    if not _tap(adb, serial, node):
        return False
    _pause(0.5, 0.9)
    # Select-all + delete: MOVE_END then a burst of DEL keyevents
    _shell(adb, serial, "input keyevent 123", timeout=15)
    _shell(adb, serial, "input keyevent " + " ".join(["67"] * 40),
           timeout=20)
    _type_text(adb, serial, value)
    _pause(0.5, 0.9)
    return True


def _edittexts(nodes):
    return [n for n in nodes if "EditText" in n["cls"]]


def _tap_text(adb, serial, nodes, texts, timeout=15):
    node = _find(_wait_screen(adb, serial, texts, timeout=timeout), texts)
    if node:
        _tap(adb, serial, node)
        _pause(1.2, 2.2)
        return True
    return False


def _log_screen(nodes, label):
    seen = sorted({n["text"] for n in nodes if n["text"]})[:18]
    with print_lock:
        print(f"{YELLOW}[Lite] {label}. Screen par ye texts mile: {seen}{WHITE}")


# ----------------------------------------------------------------------
# Identity generation (same conventions as the other modes)
# ----------------------------------------------------------------------
def _gen_identity():
    if _HAS_FAKER:
        fake = Faker()
        for _ in range(20):
            first = fake.first_name()
            last = fake.last_name()
            if (first.lower() not in _BLOCKED_NAMES
                    and last.lower() not in _BLOCKED_NAMES):
                break
    else:
        first = random.choice(["James", "Mary", "Ahmed", "Fatima", "David",
                               "Sarah", "Usman", "Ayesha", "Kevin", "Anna"])
        last = random.choice(["Smith", "Khan", "Ali", "Brown", "Ahmad",
                              "Wilson", "Hussain", "Taylor", "Iqbal"])
    low = first.strip().lower()
    if low in _MALE_FIRST:
        gender = "Male"
    elif low in _FEMALE_FIRST:
        gender = "Female"
    else:
        gender = "Male"
    # Date of birth: age 19-39
    year = random.randint(1987, 2006)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return {"first": first, "last": last, "gender": gender,
            "dob": (day, month, year)}


def _get_password(password_config):
    if (password_config and password_config.get("type") == "fixed"
            and password_config.get("value")):
        return password_config["value"]
    from core.password_manager import generate_random_password
    return generate_random_password()


# ----------------------------------------------------------------------
# Facebook Lite app management
# ----------------------------------------------------------------------
def _lite_installed(adb, serial):
    try:
        out = _shell(adb, serial, f"pm list packages {LITE_PACKAGE}",
                     timeout=25).stdout
        return LITE_PACKAGE in out
    except Exception:
        return False


def _reset_lite(adb, serial):
    """Fresh start for the next account: stop Lite and wipe its data."""
    try:
        _shell(adb, serial, f"am force-stop {LITE_PACKAGE}", timeout=20)
        _shell(adb, serial, f"pm clear {LITE_PACKAGE}", timeout=25)
    except Exception:
        pass


def _launch_lite(adb, serial):
    _shell(adb, serial,
           f"monkey -p {LITE_PACKAGE} -c android.intent.category.LAUNCHER 1",
           timeout=30)
    _pause(3.0, 5.0)


# ----------------------------------------------------------------------
# One account signup inside Facebook Lite
# ----------------------------------------------------------------------
def lite_create_account(adb, serial, identity, password, contact,
                        counter=None):
    """Drive one signup in the Lite app.

    contact: ("email", address) or ("phone", number)
    Returns dict: status success / verification_pending / failed / error
    with result_line for saving.
    """
    first, last = identity["first"], identity["last"]
    day, month, year = identity["dob"]
    gender = identity["gender"]
    kind, address = contact
    result_line = (f"{address}|{password}|{first} {last}|"
                   f"{day:02d}-{month:02d}-{year}|{gender}|facebook_lite")

    def _fail(reason):
        if counter:
            counter.update("failed")
        return {"status": "failed", "reason": reason,
                "result_line": result_line}

    try:
        _reset_lite(adb, serial)
        _launch_lite(adb, serial)

        # --- Welcome screen: Create new account ---
        nodes = _wait_screen(adb, serial, TEXTS["create_account"],
                             timeout=30)
        if not _screen_has(nodes, TEXTS["create_account"]):
            _log_screen(nodes, "Create account wala button nahi mila")
            return _fail("no_create_button")
        _tap_text(adb, serial, nodes, TEXTS["create_account"])
        _pause(2.0, 3.5)

        # --- Name step (kuch versions me ek hi full-name khana hota hai) ---
        nodes = _dump_nodes(adb, serial)
        fields = _edittexts(nodes)
        if len(fields) < 2:
            nodes = _wait_screen(adb, serial, [first[:1]], timeout=5)
            fields = _edittexts(_dump_nodes(adb, serial))
        if len(fields) >= 2:
            _fill_field(adb, serial, fields[0], first)
            _fill_field(adb, serial, fields[1], last)
        elif len(fields) == 1:
            _fill_field(adb, serial, fields[0], f"{first} {last}")
        else:
            _log_screen(_dump_nodes(adb, serial),
                        "Name ka khana nahi mila")
            return _fail("name_fields_missing")
        with print_lock:
            print(f"{GREEN}[Lite] Name: {first} {last}{WHITE}")
        _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
        _pause(2.0, 3.5)

        # --- DOB + Gender: in steps ki tartib Lite versions me alag
        #     hoti hai, is liye jo screen pehle aye wahi pehle handle
        #     hoti hai (gender screen par koi EditText nahi hota) ---
        def _do_dob():
            nodes = _dump_nodes(adb, serial)
            fields = _edittexts(nodes)
            if len(fields) >= 3:
                # Typed fields (day / month / year, in on-screen order)
                _fill_field(adb, serial, fields[0], str(day))
                _fill_field(adb, serial, fields[1], str(month))
                _fill_field(adb, serial, fields[2], str(year))
            elif _find(nodes, cls_contains="DatePicker") or \
                    _find(nodes, cls_contains="NumberPicker"):
                # Spinner picker: ek dafa khud set karo (Outlook ke
                # manual CAPTCHA wala hi tareeka)
                with print_lock:
                    print(f"{YELLOW}[Lite] DOB picker aya hai - emulator "
                          f"me khud set karo: "
                          f"{day:02d}-{month:02d}-{year}{WHITE}")
                input(f"{CYAN}[Lite] DOB set karke Enter dabao: {WHITE}")
            with print_lock:
                print(f"{GREEN}[Lite] DOB: {day:02d}-{month:02d}-{year}"
                      f"{WHITE}")
            _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
            _pause(2.0, 3.5)

        def _do_gender():
            nodes = _dump_nodes(adb, serial)
            gnode = _find(nodes, TEXTS["gender"][gender])
            if gnode:
                _tap(adb, serial, gnode)
                _pause(0.8, 1.5)
            with print_lock:
                print(f"{GREEN}[Lite] Gender: {gender}{WHITE}")
            _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
            _pause(2.0, 3.5)

        _first_screen = _dump_nodes(adb, serial)
        if _screen_has(_first_screen, TEXTS["gender_markers"]) and \
                not _edittexts(_first_screen):
            _do_gender()
            _do_dob()
        else:
            _do_dob()
            _do_gender()

        # --- Contact step (email or phone); kuch versions me isi
        #     screen par password ka khana bhi sath hota hai ---
        _password_done = False
        nodes = _dump_nodes(adb, serial)
        if kind == "email":
            # Lite defaults to mobile number; switch to email if offered
            if _find(nodes, TEXTS["signup_with_email"]):
                _tap_text(adb, serial, nodes, TEXTS["signup_with_email"])
                _pause(1.5, 2.5)
                nodes = _dump_nodes(adb, serial)
        fields = _edittexts(nodes)
        if not fields:
            _log_screen(nodes, "Contact ka khana nahi mila")
            return _fail("contact_field_missing")
        _fill_field(adb, serial, fields[0], address)
        for _extra in fields[1:]:
            if _extra.get("password"):
                _fill_field(adb, serial, _extra, password)
                _password_done = True
        with print_lock:
            print(f"{GREEN}[Lite] {kind}: {address}{WHITE}")
        _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
        _pause(2.0, 3.5)

        # --- Password step (agar contact screen par na hua ho) ---
        if not _password_done:
            nodes = _dump_nodes(adb, serial)
            fields = _edittexts(nodes)
            if not fields:
                _log_screen(nodes, "Password ka khana nahi mila")
                return _fail("password_field_missing")
            _fill_field(adb, serial, fields[0], password)
            _tap_text(adb, serial, _dump_nodes(adb, serial),
                      TEXTS["next"])
            _pause(2.5, 4.0)

        # --- Final Sign Up button / terms screen ---
        nodes = _dump_nodes(adb, serial)
        if _find(nodes, TEXTS["signup_button"]):
            _tap_text(adb, serial, nodes, TEXTS["signup_button"])
            _pause(4.0, 6.0)

        # --- Post-signup: dialogs, confirmation code, outcome ---
        for _round in range(6):
            nodes = _dump_nodes(adb, serial)
            blob_hit = _screen_has(nodes, TEXTS["blocked"])
            if blob_hit:
                _log_screen(nodes, "Facebook ne confirmation/block screen "
                                   "dikhaya hai")
                if counter:
                    counter.update("success")
                return {"status": "success",
                        "reason": "profile_verification_pending",
                        "result_line": result_line}
            if _screen_has(nodes, TEXTS["code_prompt"]):
                with print_lock:
                    print(f"{YELLOW}[Lite] Confirmation code wala screen "
                          f"hai - {address} par aya code yahan likho{WHITE}")
                code = input(f"{CYAN}[Lite] Code: {WHITE}").strip()
                cfields = _edittexts(_dump_nodes(adb, serial))
                if code and cfields:
                    _fill_field(adb, serial, cfields[0], code)
                    _tap_text(adb, serial, _dump_nodes(adb, serial),
                              TEXTS["confirm"] + TEXTS["next"])
                    _pause(3.0, 5.0)
                continue
            dismiss = _find(nodes, TEXTS["dismiss_dialog"])
            if dismiss and dismiss["clickable"]:
                _tap(adb, serial, dismiss)
                _pause(1.5, 2.5)
                continue
            if _screen_has(nodes, TEXTS["feed_markers"]):
                with print_lock:
                    print(f"{GREEN}[Lite] SUCCESS: {address}{WHITE}")
                if counter:
                    counter.update("success")
                return {"status": "success", "result_line": result_line}
            _pause(2.0, 3.0)

        # Ambiguous end state: save as pending so nothing is lost
        _log_screen(_dump_nodes(adb, serial),
                    "Aakhri screen wazeh nahi - pending save ho raha hai")
        if counter:
            counter.update("success")
        return {"status": "success",
                "reason": "profile_verification_pending",
                "result_line": result_line}

    except Exception as e:
        with print_lock:
            print(f"{RED}[Lite] Error: {e}{WHITE}")
        if counter:
            counter.update("error")
        return {"status": "error", "reason": str(e),
                "result_line": result_line}


# ----------------------------------------------------------------------
# Proxy support - PERMANENT: proxies.txt se auto-load, har account par
# agli proxy rotation se lagti hai, terminal par kuch set nahi karna.
# ----------------------------------------------------------------------
def _load_lite_proxies():
    """proxies.txt wali proxies ko {host, port, username, password}
    ki shakal me do (project ke apne proxy loader se)."""
    try:
        from core.proxy_manager import (load_proxies_from_file,
                                        format_proxy_for_playwright)
        from urllib.parse import urlparse
        out = []
        for _pd in load_proxies_from_file(verbose=False) or []:
            _pw = format_proxy_for_playwright(_pd)
            if not _pw:
                continue
            _u = urlparse(_pw["server"])
            if _u.hostname and _u.port:
                out.append({"host": _u.hostname, "port": _u.port,
                            "username": _pw.get("username"),
                            "password": _pw.get("password")})
        return out
    except Exception:
        return []


def _find_emulator_exe(adb):
    """adb ke sath wale SDK folder me emulator ka program dhundo."""
    try:
        sdk_root = os.path.dirname(os.path.dirname(os.path.abspath(adb)))
        for name in ("emulator.exe", "emulator"):
            cand = os.path.join(sdk_root, "emulator", name)
            if os.path.isfile(cand):
                return cand
    except Exception:
        pass
    return None


def _apply_android_proxy(adb, serial, proxy, state):
    """Device par proxy lagao. Wapas batata hai kis tareekay se lagi:
    'settings'  - bina-password proxy, Android ki global setting se
                  (emulator aur asli phone, dono par chalti hai)
    'emulator'  - password wali proxy: emulator ko -http-proxy ke
                  sath dobara launch karke (sirf emulator par mumkin)
    'auth_unsupported' - asli phone + password wali proxy: Android ka
                  system proxy username/password support hi nahi karta
    'none'      - proxy nahi lagi
    """
    if not proxy or not proxy.get("host") or not proxy.get("port"):
        return "none"
    host, port = proxy["host"], proxy["port"]
    if not proxy.get("username"):
        try:
            _shell(adb, serial,
                   f"settings put global http_proxy {host}:{port}",
                   timeout=20)
            return "settings"
        except Exception:
            return "none"
    if not serial.startswith("emulator"):
        return "auth_unsupported"
    try:
        emu = _find_emulator_exe(adb)
        if not emu:
            return "auth_unsupported"
        avd = state.get("avd")
        if not avd:
            out = _adb(adb, serial, "emu", "avd", "name",
                       timeout=20).stdout
            avd = out.strip().splitlines()[0].strip() if out.strip() else ""
            state["avd"] = avd
        if not avd:
            return "auth_unsupported"
        proxy_url = (f"http://{proxy['username']}:"
                     f"{proxy.get('password') or ''}@{host}:{port}")
        _adb(adb, serial, "emu", "kill", timeout=20)
        time.sleep(5)
        subprocess.Popen(
            [emu, "-avd", avd, "-http-proxy", proxy_url,
             "-no-snapshot-load"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        _adb(adb, serial, "wait-for-device", timeout=120)
        for _ in range(40):
            try:
                boot = _shell(adb, serial,
                              "getprop sys.boot_completed",
                              timeout=15).stdout.strip()
            except Exception:
                boot = ""
            if boot == "1":
                break
            time.sleep(3)
        _pause(2.0, 4.0)
        return "emulator"
    except Exception:
        return "none"


def _clear_android_proxy(adb, serial):
    try:
        _shell(adb, serial, "settings put global http_proxy :0",
               timeout=20)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Mode entry point (called from main.py: Mode 2 -> Android Setup)
# ----------------------------------------------------------------------
def _load_saved_emails():
    """Emails from the Outlook mode's saved accounts, if the file exists
    (first field of each line, before the | separator)."""
    try:
        from core.path_manager import get_output_dir
        path = os.path.join(get_output_dir(), "outlook_accounts.txt")
        if not os.path.isfile(path):
            return []
        emails = []
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                first_field = line.split("|")[0].strip()
                if "@" in first_field:
                    emails.append(first_field)
        return emails
    except Exception:
        return []


def run_android_lite_mode(count, password_config, counter=None):
    """Create `count` Facebook accounts inside the Facebook Lite app
    on one connected Android emulator/device (ADB)."""
    with print_lock:
        print(f"\n{CYAN}[Lite] === FB Lite Android Mode (Facebook Lite "
              f"app only) ==={WHITE}")

    adb = _find_adb()
    if not adb:
        with print_lock:
            print(f"{RED}[Lite] adb nahi mila! Android SDK platform-tools "
                  f"install karo (ya apne Android Emulator Launcher se ek "
                  f"device banao - usi SDK me adb hota hai), phir dobara "
                  f"try karo.{WHITE}")
        return

    devices = _list_devices(adb)
    if not devices:
        with print_lock:
            print(f"{RED}[Lite] Koi Android device/emulator connected "
                  f"nahi hai. Pehle emulator launch karo (apne launcher "
                  f"se) ya phone USB debugging ON karke lagao, phir "
                  f"dobara try karo.{WHITE}")
        return
    serial = devices[0]
    if len(devices) > 1:
        with print_lock:
            for i, d in enumerate(devices, 1):
                print(f" {GREEN}[{RED}0{i}{GREEN}] {d}{WHITE}")
        try:
            pick = int(input(f" {GREEN}[{RED}●{GREEN}] Device number "
                             f"[1] {EKL} ").strip() or "1")
            serial = devices[pick - 1]
        except Exception:
            serial = devices[0]
    with print_lock:
        print(f"{GREEN}[Lite] Device: {serial}{WHITE}")

    if not _lite_installed(adb, serial):
        with print_lock:
            print(f"{YELLOW}[Lite] Is device par Facebook Lite installed "
                  f"nahi hai.{WHITE}")
        apk = input(f" {GREEN}[{RED}●{GREEN}] Lite APK ka full path "
                    f"(khali = Play Store se khud install karke dobara "
                    f"chalao) {EKL} ").strip().strip('"')
        if apk and os.path.isfile(apk):
            with print_lock:
                print(f"{CYAN}[Lite] APK install ho raha hai...{WHITE}")
            _adb(adb, serial, "install", "-r", apk, timeout=180)
        if not _lite_installed(adb, serial):
            with print_lock:
                print(f"{RED}[Lite] Facebook Lite ab bhi nahi mila - "
                      f"mode band ho raha hai.{WHITE}")
            return
    with print_lock:
        print(f"{GREEN}[Lite] Facebook Lite tayyar hai{WHITE}")

    # Permanent proxy: proxies.txt khud load hoti hai, har account par
    # agli proxy lagti hai - terminal par kabhi set nahi karna padta
    lite_proxies = _load_lite_proxies()
    proxy_state = {"avd": None, "warned": False, "via_settings": False}
    if lite_proxies:
        # Proxies OPTIONAL hain - user ki marzi, 'n' par direct chalega
        try:
            _ans = input(f" {GREEN}[{RED}●{GREEN}] proxies.txt se "
                         f"{len(lite_proxies)} proxies mili hain - use "
                         f"karni hain? (y/n) [y] {EKL} ").strip().lower()
        except Exception:
            _ans = "y"
        if _ans == "n":
            lite_proxies = []
            with print_lock:
                print(f"{CYAN}[Lite] Theek hai - proxies use nahi "
                      f"hongi, direct connection{WHITE}")
    with print_lock:
        if lite_proxies:
            print(f"{GREEN}[Lite] proxies.txt active: "
                  f"{len(lite_proxies)} proxies - har account par agli "
                  f"proxy khud lagegi{WHITE}")
        else:
            print(f"{CYAN}[Lite] Direct connection{WHITE}")

    # Contact choice: saved Outlook emails, typed emails, or phone numbers
    saved_emails = _load_saved_emails()
    if saved_emails:
        with print_lock:
            print(f" {GREEN}[{RED}01{GREEN}] Email - saved Outlook "
                  f"accounts se ({len(saved_emails)} mile){WHITE}")
            print(f" {GREEN}[{RED}02{GREEN}] Email - har account ke liye "
                  f"khud likhunga{WHITE}")
            print(f" {GREEN}[{RED}03{GREEN}] Mobile number - har account "
                  f"ke liye khud likhunga{WHITE}")
        src = input(f" {GREEN}[{RED}●{GREEN}] Select (1/2/3) [1] "
                    f"{EKL} ").strip() or "1"
    else:
        with print_lock:
            print(f" {GREEN}[{RED}01{GREEN}] Email - har account ke liye "
                  f"khud likhunga{WHITE}")
            print(f" {GREEN}[{RED}02{GREEN}] Mobile number - har account "
                  f"ke liye khud likhunga{WHITE}")
        src = input(f" {GREEN}[{RED}●{GREEN}] Select (1/2) [1] "
                    f"{EKL} ").strip() or "1"
        src = {"1": "2", "2": "3"}.get(src, "2")

    email_iter = iter(saved_emails) if src == "1" else None

    from core.counter import Counter
    if counter is None:
        counter = Counter()

    for idx in range(1, count + 1):
        with print_lock:
            print(f"\n{CYAN}[Lite] --- Account {idx}/{count} ---{WHITE}")
        if email_iter is not None:
            address = next(email_iter, None)
            if not address:
                with print_lock:
                    print(f"{YELLOW}[Lite] Saved emails khatam - mode "
                          f"ruk raha hai.{WHITE}")
                break
            contact = ("email", address)
        elif src == "2":
            address = input(f" {GREEN}[{RED}●{GREEN}] Is account ke liye "
                            f"email {EKL} ").strip()
            if not address:
                with print_lock:
                    print(f"{YELLOW}[Lite] Email khali - skip{WHITE}")
                continue
            contact = ("email", address)
        else:
            number = input(f" {GREEN}[{RED}●{GREEN}] Is account ke liye "
                           f"mobile number {EKL} ").strip()
            if not number:
                with print_lock:
                    print(f"{YELLOW}[Lite] Number khali - skip{WHITE}")
                continue
            contact = ("phone", number)

        identity = _gen_identity()
        password = _get_password(password_config)
        if lite_proxies:
            _px = lite_proxies[(idx - 1) % len(lite_proxies)]
            _via = _apply_android_proxy(adb, serial, _px, proxy_state)
            if _via == "settings":
                proxy_state["via_settings"] = True
            with print_lock:
                if _via in ("settings", "emulator"):
                    print(f"{GREEN}[Lite] Proxy lag gayi "
                          f"({_px['host']}:{_px['port']}){WHITE}")
                elif _via == "auth_unsupported" and \
                        not proxy_state["warned"]:
                    proxy_state["warned"] = True
                    print(f"{YELLOW}[Lite] NOTE: ye password wali proxy "
                          f"hai aur device asli phone hai - Android ka "
                          f"system proxy password support nahi karta. "
                          f"Emulator par yehi proxy khud lag jayegi, ya "
                          f"apne proxy provider par apna IP whitelist "
                          f"kar lo (phir password ki zaroorat nahi "
                          f"rehti). Abhi direct chal raha hai.{WHITE}")
        result = lite_create_account(adb, serial, identity, password,
                                     contact, counter)

        if result["status"] == "success":
            try:
                from core.path_manager import get_output_dir
                output_dir = get_output_dir()
                os.makedirs(output_dir, exist_ok=True)
                with open(os.path.join(output_dir,
                                       "android_lite_accounts.txt"),
                          "a", encoding="utf-8") as fh:
                    fh.write(result["result_line"] + "\n")
                note = (" (verification pending)"
                        if result.get("reason")
                        == "profile_verification_pending" else "")
                with print_lock:
                    print(f"{GREEN}[Lite] Saved: "
                          f"{result['result_line'].split('|')[0]}"
                          f"{note}{WHITE}")
            except Exception as e:
                with print_lock:
                    print(f"{RED}[Lite] Save error: {e}{WHITE}")
        else:
            with print_lock:
                print(f"{RED}[Lite] Failed: "
                      f"{result.get('reason', result['status'])}{WHITE}")

        if idx < count:
            _reset_lite(adb, serial)
            _pause(20.0, 40.0)

    if proxy_state.get("via_settings"):
        _clear_android_proxy(adb, serial)
    with print_lock:
        print(f"\n{GREEN}[Lite] Mode khatam. Accounts file: "
              f"android_lite_accounts.txt{WHITE}")
