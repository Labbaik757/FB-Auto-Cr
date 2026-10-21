"""FB Auto Create -> Android Setup: Facebook account creation inside
the Facebook Lite ANDROID app (package com.facebook.lite), selected
from Mode 2 (FB Auto Create) in main.py. The original Browser Setup
is untouched; this is a separate, self-contained module.

Drives the real Lite app over ADB + uiautomator UI dumps - on a PC
(emulator or USB phone) or in Termux on the phone itself (Wireless
ADB). No extra pip packages; Faker identities like the other modes.

Facebook Lite only - the regular Facebook app and the mobile site
are not supported here.
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
# Facebook Lite versions differ in wording and step order, so all
# known variants live here and the flow keys off what is actually
# on screen, not a fixed step order.
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
    "resend_expander": ["Didn't get the code", "Didn't receive a code",
                        "Need another way", "Try another way",
                        "More options"],
    "resend": ["Resend code", "Resend SMS", "Send code again",
               "Resend", "Send again"],
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
        os.path.join(os.environ.get("ANDROID_SDK_ROOT", ""),
                     "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("ANDROID_SDK_ROOT", ""),
                     "platform-tools", "adb"),
        # Termux: android-tools adb
        os.path.join(os.environ.get("PREFIX", ""), "bin", "adb"),
        "/data/data/com.termux/files/usr/bin/adb",
        # Bundled platform-tools next to the tool
        os.path.join(os.getcwd(), "platform-tools", "adb.exe"),
        os.path.join(os.getcwd(), "platform-tools", "adb"),
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


def _is_termux():
    """True when running inside Termux (on the Android phone)."""
    return "com.termux" in os.environ.get("PREFIX", "")


def _clean_port(text):
    """Normalize a port entry: a pasted '192.168.1.5:35907' yields
    just 35907; a plain number passes through; junk yields ''.
    """
    text = (text or "").strip()
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits


def _try_mdns_connect(adb):
    """Discover the phone's wireless connect address via mDNS and
    connect. With an already-trusted key this needs no prompts.
    Returns the endpoint or None.
    """
    try:
        res = subprocess.run([adb, "mdns", "services"],
                             capture_output=True, text=True, timeout=25)
        _m = re.search(r"_adb-tls-connect\._tcp\s+"
                       r"(\d+\.\d+\.\d+\.\d+:\d+)",
                       (res.stdout or "") + (res.stderr or ""))
        if _m:
            _adb(adb, None, "connect", _m.group(1), timeout=20)
            return _m.group(1)
    except Exception:
        pass
    return None


def _connect_own_phone(adb):
    """Self-connect from Termux to this phone over Wireless ADB, so
    the tool drives this phone's own Lite app. Needs Wireless
    debugging ON; pairing is one-time.
    """
    # Already paired: plain connect works
    try:
        _adb(adb, None, "connect", "localhost:5555", timeout=15)
    except Exception:
        pass
    if _list_devices(adb):
        return True
    # Trusted key (PC pairing + key copy): connect silently,
    # no pairing prompts needed
    if _try_mdns_connect(adb) and _list_devices(adb):
        with print_lock:
            print(f"{GREEN}[Lite] Connected - key already trusted, "
                  f"no pairing needed{WHITE}")
        return True
    with print_lock:
        print(f"\n{YELLOW}[Lite] Termux: one-time Wireless ADB "
              f"pairing - open 'Pair device with pairing code' on "
              f"the phone and enter its port + code below.{WHITE}")
    # Up to 3 pairing attempts in place - some phones kill the
    # dialog in the background ("protocol fault"), so be quick.
    paired = False
    for _try in range(1, 4):
        if _try > 1:
            with print_lock:
                print(f"{YELLOW}[Lite] Retry ({_try}/3): reopen the "
                      f"pairing dialog for a fresh port + code"
                      f"{WHITE}")
        pair_port = _clean_port(input(f" {GREEN}[{RED}●{GREEN}] "
                                      f"Pairing dialog 'IP address & "
                                      f"Port' {EKL} "))
        pair_code = input(f" {GREEN}[{RED}●{GREEN}] Pairing dialog "
                          f"'Wi-Fi pairing code' (6 digits) {EKL} "
                          ).strip()
        if not (pair_port and pair_code):
            continue
        try:
            res = subprocess.run(
                [adb, "pair", f"localhost:{pair_port}"],
                input=pair_code + "\n", capture_output=True, text=True,
                timeout=40)
            _out = ((res.stdout or "") + (res.stderr or "")).strip()
            with print_lock:
                print(f"{GREEN}[Lite] Pairing: {_out}{WHITE}")
            if "CANNOT LINK EXECUTABLE" in _out:
                with print_lock:
                    print(f"{RED}[Lite] Termux adb cannot run - a "
                          f"package is missing. Exit and run:{WHITE}")
                    print(f"{YELLOW}    pkg install libc++{WHITE}")
                    print(f"{RED}[Lite] Then start again.{WHITE}")
                return False
            if "Successfully paired" in _out:
                paired = True
                break
            with print_lock:
                if "protocol fault" in _out:
                    print(f"{RED}[Lite] Pairing failed: the dialog "
                          f"closed before the code arrived - retry "
                          f"quickly.{WHITE}")
                else:
                    print(f"{RED}[Lite] Pairing failed - check the "
                          f"port and code, then retry.{WHITE}")
        except Exception as e:
            with print_lock:
                print(f"{RED}[Lite] Pairing error: {e}{WHITE}")
    if not paired:
        return False
    # Connect port is auto-discovered via mDNS
    if not _list_devices(adb):
        _found = _try_mdns_connect(adb)
        if _found:
            with print_lock:
                print(f"{CYAN}[Lite] Connect port found: "
                      f"{_found}{WHITE}")
    if not _list_devices(adb):
        # Last resort: ask for the main-window port
        with print_lock:
            print(f"{YELLOW}[Lite] Connect port not found "
                  f"automatically - enter the 'IP address & Port' "
                  f"from the Wireless debugging main window.{WHITE}")
        conn_port = _clean_port(input(f" {GREEN}[{RED}●{GREEN}] "
                                      f"Main window 'IP address & "
                                      f"Port' {EKL} "))
        if conn_port:
            try:
                _adb(adb, None, "connect", f"localhost:{conn_port}",
                     timeout=20)
            except Exception:
                pass
    return bool(_list_devices(adb))


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
        time.sleep(1.2)
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
    # Reuse the current dump first (each dump costs 1-3s on a
    # phone); only wait and re-dump when not found.
    node = _find(nodes, texts)
    if not node:
        node = _find(_wait_screen(adb, serial, texts,
                                  timeout=timeout), texts)
    if node:
        _tap(adb, serial, node)
        _pause(1.0, 1.8)
        return True
    return False


def _log_screen(nodes, label):
    seen = sorted({n["text"] for n in nodes if n["text"]})[:18]
    with print_lock:
        print(f"{YELLOW}[Lite] {label}. On-screen texts: {seen}{WHITE}")


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
    _pause(2.5, 4.0)


def _find_lite_apks():
    """APK files stocked in a `lite_apks` folder (several Lite
    versions). One version installs per account - version rotation.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "lite_apks"),
        os.path.join(here, "..", "lite_apks"),
        os.path.join(os.path.expanduser("~"), "lite_apks"),
        "/sdcard/lite_apks",
    ]
    for folder in candidates:
        try:
            folder = os.path.normpath(folder)
            if os.path.isdir(folder):
                apks = sorted(
                    os.path.join(folder, f) for f in os.listdir(folder)
                    if f.lower().endswith(".apk"))
                if apks:
                    return apks
        except Exception:
            continue
    return []


def _lite_version_name(adb, serial):
    try:
        out = _shell(
            adb, serial,
            f"dumpsys package {LITE_PACKAGE} | grep versionName",
            timeout=25).stdout
        for part in out.replace("=", " ").split():
            if part and part[0].isdigit() and "." in part:
                return part
    except Exception:
        pass
    return "?"


# ----------------------------------------------------------------------
# AUTO SETUP (one-time): folders are created and a few Lite
# versions are stocked automatically - once only.
_LITE_DOWNLOAD_SOURCES = [
    ("latest", "https://d.apkpure.com/b/APK/com.facebook.lite"
                 "?version=latest"),
    ("older-1", "https://d.apkpure.com/b/APK/com.facebook.lite"
                "?version=437.0.0.0.86"),
    ("older-2", "https://d.apkpure.com/b/APK/com.facebook.lite"
                "?version=402.0.0.0.97"),
]


def _lite_apk_dirs():
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.normpath(p) for p in (
        os.path.join(os.getcwd(), "lite_apks"),
        os.path.join(here, "..", "lite_apks"),
        os.path.join(os.path.expanduser("~"), "lite_apks"),
        "/sdcard/lite_apks")]


def _apk_ok(path):
    """True when a downloaded/pulled file is a real APK (size + PK magic)."""
    try:
        if os.path.getsize(path) < 1_000_000:
            return False
        with open(path, "rb") as fh:
            return fh.read(2) == b"PK"
    except Exception:
        return False


def _pull_installed_lite_apk(adb, serial, dest_dir):
    """Pull the phone's own installed Lite APK into the folder -
    the safest version, being the phone's official installed app.
    The version is part of the filename.
    """
    out = _adb(adb, serial, "shell", "pm", "path",
               LITE_PACKAGE).stdout
    remote = ""
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("package:") and line.endswith("base.apk"):
            remote = line[len("package:"):]
            break
    if not remote:
        return None
    ver = _lite_version_name(adb, serial).replace(" ", "_") or "phone"
    dest = os.path.join(dest_dir, f"facebook-lite-{ver}-phone.apk")
    if os.path.exists(dest):
        return dest
    _adb(adb, serial, "pull", remote, dest, timeout=180)
    if _apk_ok(dest):
        return dest
    try:
        os.remove(dest)
    except Exception:
        pass
    return None


def _download_lite_apk(url, dest):
    """Download one Lite version into the folder; drop it on failure."""
    try:
        import requests
        with requests.get(
                url, stream=True, timeout=60,
                headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13)"}
        ) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(262144):
                    if chunk:
                        fh.write(chunk)
    except Exception:
        pass
    if _apk_ok(dest):
        return True
    try:
        os.remove(dest)
    except Exception:
        pass
    return False


def _ensure_lite_setup(adb, serial):
    """One-time auto setup: (1) lite_apks folder, (2) output
    folder, (3) Lite versions - when fewer than 2 are stocked, pull
    the phone's own Lite and try downloads. No-op at 2+ versions.
    """
    # 1) lite_apks folder
    dest_dir = None
    for d in _lite_apk_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            if dest_dir is None:
                dest_dir = d
        except Exception:
            continue
    # 2) Output folder (inside the repo folder, like Browser Setup)
    try:
        os.makedirs(os.path.join(
            os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "output"),
            exist_ok=True)
    except Exception:
        pass
    # 4) Versions - skip when 2+ already stocked
    if len(_find_lite_apks()) >= 2 or dest_dir is None:
        return
    with print_lock:
        print(f"{CYAN}[Lite] Stocking Lite versions "
              f"(one-time)...{WHITE}")
    got = []
    if serial:
        pulled = _pull_installed_lite_apk(adb, serial, dest_dir)
        if pulled:
            got.append(pulled)
            with print_lock:
                print(f"{GREEN}[Lite] Stocked the phone's own Lite: "
                      f"{os.path.basename(pulled)}{WHITE}")
    seen = set()
    for _p in _find_lite_apks():
        try:
            seen.add(os.path.getsize(_p))
        except Exception:
            pass
    for label, url in _LITE_DOWNLOAD_SOURCES:
        if len(_find_lite_apks()) >= 3:
            break
        dest = os.path.join(dest_dir, f"facebook-lite-{label}.apk")
        if os.path.exists(dest):
            continue
        if _download_lite_apk(url, dest):
            try:
                size = os.path.getsize(dest)
            except Exception:
                size = 0
            if size in seen:  # Same file again - drop it
                try:
                    os.remove(dest)
                except Exception:
                    pass
                continue
            seen.add(size)
            got.append(dest)
            with print_lock:
                print(f"{GREEN}[Lite] Downloaded and stocked: "
                      f"facebook-lite-{label}.apk{WHITE}")
    total = len(_find_lite_apks())
    with print_lock:
        if total >= 2:
            print(f"{GREEN}[Lite] {total} Lite versions stocked in "
                  f"lite_apks - one per account{WHITE}")
        elif total == 1:
            print(f"{YELLOW}[Lite] Only 1 version stocked - add "
                  f"more APKs to this folder for rotation: "
                  f"{dest_dir}{WHITE}")
        else:
            print(f"{YELLOW}[Lite] No version could be stocked "
                  f"automatically - continuing with the installed "
                  f"one. To add versions, put APKs in: "
                  f"{dest_dir}{WHITE}")


def _install_lite_apk(adb, serial, apk_path):
    """Install one Lite version (-d allows downgrades, so rotation
    works in both directions).
    """
    try:
        res = _adb(adb, serial, "install", "-r", "-d", apk_path,
                   timeout=300)
        blob = (res.stdout or "") + (res.stderr or "")
        return "Success" in blob
    except Exception:
        return False


def _wait_device_back(adb, tries=30):
    """Wait for wireless ADB to return after an airplane/Wi-Fi
    toggle (up to ~60 seconds).
    """
    for _ in range(tries):
        try:
            _adb(adb, None, "reconnect", timeout=15)
        except Exception:
            pass
        if _list_devices(adb):
            return True
        time.sleep(2)
    return False


def _parse_lite_number_entry(entry):
    """Split one Number_List entry - same rule as Browser Setup's
    _parse_number_entry: 'number,url' or 'number|url'; '#' and
    blank lines are skipped. Returns (number, sms_url or None).
    """
    entry = (entry or "").strip()
    if entry.startswith("#") or not entry:
        return None, None
    for sep in [",", "|"]:
        if sep in entry:
            parts = entry.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return entry, None


# ----------------------------------------------------------------------
# OTP auto-fetch: with an SMS link on the number, the code is
# fetched and entered automatically - Browser Setup logic.
def _fetch_otp_from_sms_url(sms_url, timeout=7, interval=1):
    """Fetch the OTP from an SMS link (Browser Setup method): GET
    the link, plain-text reply; a 'no' prefix means no code yet;
    the first 4-8 digit number is the code. Polls until timeout.
    """
    import requests
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(sms_url, timeout=15)
            text = (r.text or "").strip()
            if text and not text.startswith("no"):
                m = re.search(r"\d{4,8}", text)
                if m:
                    return m.group(0)
        except Exception:
            pass
        time.sleep(interval)
    return None


def _tap_resend_in_lite(adb, serial):
    """Tap Resend in Lite: open the expander that hides it
    ('Didn't get the code'), then tap Resend. One tap per round
    here (mobile rate-limits faster than PC); 3 rounds total.
    """
    nodes = _dump_nodes(adb, serial)
    expander = _find(nodes, TEXTS["resend_expander"])
    if expander:
        _tap(adb, serial, expander)
        _pause(1.0, 1.8)
        nodes = _dump_nodes(adb, serial)
    btn = _find(nodes, TEXTS["resend"])
    if btn:
        _tap(adb, serial, btn)
        with print_lock:
            print(f"{CYAN}[Lite] Resend tapped{WHITE}")
        _pause(1.2, 2.2)
        return True
    return False


def _auto_otp_rounds(adb, serial, sms_url):
    """Resend+fetch cycle, as on PC: 3 rounds - resend, then poll
    the link ~7s. Returns the code or None.
    """
    with print_lock:
        print(f"{CYAN}[Lite] Auto-fetching OTP from SMS "
              f"link...{WHITE}")
    for _round in range(3):
        _tap_resend_in_lite(adb, serial)
        code = _fetch_otp_from_sms_url(sms_url, timeout=7, interval=1)
        if code:
            with print_lock:
                print(f"{GREEN}[Lite] OTP received: {code}{WHITE}")
            return code
        if _round < 2:
            with print_lock:
                print(f"{YELLOW}[Lite] No OTP yet, resending... "
                      f"({_round + 2}/3){WHITE}")
    return None


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
    kind = contact[0]
    address = contact[1]
    sms_url = contact[2] if len(contact) > 2 else None
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
            _log_screen(nodes, "Create-account button not found")
            return _fail("no_create_button")
        _tap_text(adb, serial, nodes, TEXTS["create_account"])
        _pause(1.2, 2.2)

        # --- Name step (some versions use a single full-name field) ---
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
                        "Name field not found")
            return _fail("name_fields_missing")
        with print_lock:
            print(f"{GREEN}[Lite] Name: {first} {last}{WHITE}")
        _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
        _pause(1.2, 2.2)

        # --- DOB + Gender: step order differs between Lite
        #     versions, so whichever screen appears first is
        #     handled first (gender screen has no EditText) ---
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
                # Spinner picker: set it once, by hand if needed
                with print_lock:
                    print(f"{YELLOW}[Lite] DOB picker shown - set it "
                          f"manually: "
                          f"{day:02d}-{month:02d}-{year}{WHITE}")
                input(f"{CYAN}[Lite] Set the DOB, then press Enter: {WHITE}")
            with print_lock:
                print(f"{GREEN}[Lite] DOB: {day:02d}-{month:02d}-{year}"
                      f"{WHITE}")
            _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
            _pause(1.2, 2.2)

        def _do_gender():
            nodes = _dump_nodes(adb, serial)
            gnode = _find(nodes, TEXTS["gender"][gender])
            if gnode:
                _tap(adb, serial, gnode)
                _pause(0.8, 1.5)
            with print_lock:
                print(f"{GREEN}[Lite] Gender: {gender}{WHITE}")
            _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
            _pause(1.2, 2.2)

        _first_screen = _dump_nodes(adb, serial)
        if _screen_has(_first_screen, TEXTS["gender_markers"]) and \
                not _edittexts(_first_screen):
            _do_gender()
            _do_dob()
        else:
            _do_dob()
            _do_gender()

        # --- Contact step (email or phone); some versions also
        #     show the password field on this same screen ---
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
            _log_screen(nodes, "Contact field not found")
            return _fail("contact_field_missing")
        _fill_field(adb, serial, fields[0], address)
        for _extra in fields[1:]:
            if _extra.get("password"):
                _fill_field(adb, serial, _extra, password)
                _password_done = True
        with print_lock:
            print(f"{GREEN}[Lite] {kind}: {address}{WHITE}")
        _tap_text(adb, serial, _dump_nodes(adb, serial), TEXTS["next"])
        _pause(1.2, 2.2)

        # --- Password step (when not shown on the contact screen) ---
        if not _password_done:
            nodes = _dump_nodes(adb, serial)
            fields = _edittexts(nodes)
            if not fields:
                _log_screen(nodes, "Password field not found")
                return _fail("password_field_missing")
            _fill_field(adb, serial, fields[0], password)
            _tap_text(adb, serial, _dump_nodes(adb, serial),
                      TEXTS["next"])
            _pause(1.8, 3.0)

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
                _log_screen(nodes, "Confirmation/block screen shown "
                                   "by Facebook")
                if counter:
                    counter.update("success")
                return {"status": "success",
                        "reason": "profile_verification_pending",
                        "result_line": result_line + "|pending"}
            if _screen_has(nodes, TEXTS["code_prompt"]):
                # SMS link present: OTP is fetched and entered
                # automatically (PC system); manual entry is last
                code = None
                if sms_url:
                    code = _auto_otp_rounds(adb, serial, sms_url)
                else:
                    _tap_resend_in_lite(adb, serial)
                if not code:
                    with print_lock:
                        print(f"{YELLOW}[Lite] Auto OTP failed - "
                              f"enter the code sent to {address} "
                              f"(blank = skip){WHITE}")
                    code = input(f"{CYAN}[Lite] Code: {WHITE}").strip()
                if not code:
                    if counter:
                        counter.update("failed")
                    return {"status": "failed", "reason": "otp_not_received",
                            "result_line": result_line}
                cfields = _edittexts(_dump_nodes(adb, serial))
                if cfields:
                    _fill_field(adb, serial, cfields[0], code)
                    _tap_text(adb, serial, _dump_nodes(adb, serial),
                              TEXTS["confirm"] + TEXTS["next"])
                    _pause(2.5, 4.0)
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
                return {"status": "success",
                        "result_line": result_line + "|confirmed"}
            _pause(1.2, 2.0)

        # Ambiguous end state: save as pending so nothing is lost
        _log_screen(_dump_nodes(adb, serial),
                    "End screen unclear - saving as pending")
        if counter:
            counter.update("success")
        return {"status": "success",
                "reason": "profile_verification_pending",
                "result_line": result_line + "|pending"}

    except Exception as e:
        with print_lock:
            print(f"{RED}[Lite] Error: {e}{WHITE}")
        if counter:
            counter.update("error")
        return {"status": "error", "reason": str(e),
                "result_line": result_line}


# ----------------------------------------------------------------------
# Proxy support: proxies.txt auto-loads and rotates one proxy per
# account; nothing is configured in the terminal.
_ANDROID_PROXY_DIRS = ["/sdcard/Download",
                       "/storage/emulated/0/Download",
                       "/sdcard"]


def _load_lite_proxies():
    """Load proxies.txt entries as {host, port, username, password}
    via the project's own proxy loader. Termux's HOME Downloads
    is not the phone's, so /sdcard/Download is checked separately.
    """
    try:
        from core.proxy_manager import (load_proxies_from_file,
                                        format_proxy_for_playwright)
        from urllib.parse import urlparse

        def _parse(_list):
            _out = []
            for _pd in _list or []:
                _pw = format_proxy_for_playwright(_pd)
                if not _pw:
                    continue
                _u = urlparse(_pw["server"])
                if _u.hostname and _u.port:
                    _out.append({"host": _u.hostname, "port": _u.port,
                                 "username": _pw.get("username"),
                                 "password": _pw.get("password")})
            return _out

        out = _parse(load_proxies_from_file(verbose=False))
        if out:
            return out
        import glob as _glob
        for folder in _ANDROID_PROXY_DIRS:
            try:
                files = sorted(_glob.glob(os.path.join(folder, "*.txt")))
            except Exception:
                continue
            for path in files:
                name = os.path.basename(path).lower()
                if "prox" not in name and "webshare" not in name:
                    continue
                try:
                    out = _parse(load_proxies_from_file(
                        filepath=path, verbose=False))
                except Exception:
                    continue
                if out:
                    with print_lock:
                        print(f"{CYAN}[Lite] Proxies loaded from: "
                              f"{path}{WHITE}")
                    return out
        return out
    except Exception:
        return []


def _find_emulator_exe(adb):
    """Find the emulator program in the SDK folder next to adb."""
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
    """Apply a proxy on the device. Returns how it was applied:
    'settings'  - no-password proxy, via Android global settings
                  (works on emulator and real phone)
    'emulator'  - auth proxy: emulator relaunched with -http-proxy
                  (emulator only)
    'auth_unsupported' - real phone + auth proxy: Android's system
                  proxy has no username/password support
    'none'      - no proxy applied
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
def run_android_lite_mode(password_config, counter=None,
                        numbers=None):
    """Create accounts in the Facebook Lite app. Numbers arrive
    via process_file_input, exactly as in Browser Setup: one
    account per number, list end = mode end, no count prompt.
    """
    with print_lock:
        print(f"\n{CYAN}[Lite] === FB Lite Android Mode (Facebook Lite "
              f"app only) ==={WHITE}")

    adb = _find_adb()
    if not adb:
        with print_lock:
            if _is_termux():
                print(f"{RED}[Lite] adb not found. In Termux run: "
                      f"pkg install android-tools, then try "
                      f"again.{WHITE}")
            else:
                print(f"{RED}[Lite] adb not found. Install the "
                      f"Android SDK platform-tools (or create a "
                      f"device with your Android Emulator Launcher - "
                      f"its SDK includes adb), then try again.{WHITE}")
        return

    devices = _list_devices(adb)
    if not devices and _is_termux():
        # Termux on the phone itself: self-connect over Wireless
        # ADB so this phone's real Lite app is the one driven
        if _connect_own_phone(adb):
            devices = _list_devices(adb)
    if not devices:
        with print_lock:
            if _is_termux():
                print(f"{RED}[Lite] ADB did not connect to the "
                      f"phone. Check Wireless debugging is ON and "
                      f"pairing succeeded, then retry.{WHITE}")
            else:
                print(f"{RED}[Lite] No Android device/emulator "
                      f"connected. Launch an emulator (via your "
                      f"launcher) or connect a phone with USB "
                      f"debugging ON, then retry.{WHITE}")
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
            print(f"{YELLOW}[Lite] Facebook Lite is not installed "
                  f"on this device.{WHITE}")
        _auto_apks = _find_lite_apks()
        if _auto_apks:
            with print_lock:
                print(f"{CYAN}[Lite] Installing the first version "
                      f"from lite_apks...{WHITE}")
            _install_lite_apk(adb, serial, _auto_apks[0])
        apk = ""
        if not _lite_installed(adb, serial):
            apk = input(f" {GREEN}[{RED}●{GREEN}] Full path to a Lite "
                        f"APK (blank = install from Play Store and "
                        f"rerun) {EKL} ").strip().strip('"')
        if apk and os.path.isfile(apk):
            with print_lock:
                print(f"{CYAN}[Lite] Installing APK...{WHITE}")
            _adb(adb, serial, "install", "-r", apk, timeout=180)
        if not _lite_installed(adb, serial):
            with print_lock:
                print(f"{RED}[Lite] Facebook Lite still not found - "
                      f"closing mode.{WHITE}")
            return
    with print_lock:
        print(f"{GREEN}[Lite] Facebook Lite ready "
              f"(version {_lite_version_name(adb, serial)}){WHITE}")

    # One-time auto setup: folders and Lite versions are stocked
    # automatically (no-op when 2+ versions already present)
    _ensure_lite_setup(adb, serial)

    # APKs for version rotation (when a lite_apks folder exists)
    lite_apks = _find_lite_apks()
    if lite_apks:
        with print_lock:
            print(f"{GREEN}[Lite] {len(lite_apks)} versions found in "
                  f"lite_apks - one installs per account{WHITE}")

    # Permanent proxies: proxies.txt auto-loads; the next proxy
    # applies per account - nothing to set in the terminal
    lite_proxies = _load_lite_proxies()
    proxy_state = {"avd": None, "warned": False, "via_settings": False}
    if lite_proxies:
        # Proxies are optional - 'n' runs direct
        try:
            _ans = input(f" {GREEN}[{RED}●{GREEN}] {len(lite_proxies)} "
                         f"proxies found in proxies.txt - use them? "
                         f"(y/n) [y] {EKL} ").strip().lower()
        except Exception:
            _ans = "y"
        if _ans == "n":
            lite_proxies = []
            with print_lock:
                print(f"{CYAN}[Lite] OK - running direct, no "
                      f"proxies{WHITE}")
    with print_lock:
        if lite_proxies:
            print(f"{GREEN}[Lite] proxies.txt active: "
                  f"{len(lite_proxies)} proxies - next proxy applies "
                  f"per account{WHITE}")
        else:
            print(f"{CYAN}[Lite] Direct connection{WHITE}")

    # No proxy + mobile data: optional manual airplane-mode
    # toggle before each account, for a fresh IP
    ip_refresh_manual = False
    if not lite_proxies:
        try:
            _ans2 = input(f" {GREEN}[{RED}●{GREEN}] Toggle airplane "
                          f"mode ON/OFF yourself before each account "
                          f"for a new IP? (mobile data only) "
                          f"(y/n) [n] {EKL} ").strip().lower()
        except Exception:
            _ans2 = "n"
        ip_refresh_manual = (_ans2 == "y")

    # Numbers via the project's own process_file_input() - the
    # exact function main.py uses for Browser Setup and HTTP
    # mode (Excel files auto-extract into Number_List.txt).
    from core.number_manager import process_file_input
    raw_numbers = (numbers if numbers is not None
                   else process_file_input())
    if raw_numbers is None:
        with print_lock:
            print(f"{RED}[Lite] No numbers loaded - closing "
                  f"Android Mode{WHITE}")
        return
    queue = []
    for _entry in raw_numbers:
        _num, _url = _parse_lite_number_entry(_entry)
        if _num:
            queue.append(("phone", _num, _url))
    total = len(queue)
    if not total:
        with print_lock:
            print(f"{RED}[Lite] No usable number found - closing "
                  f"Android Mode{WHITE}")
        return

    from core.counter import Counter
    if counter is None:
        counter = Counter()

    idx = 0
    while idx < total:
        contact = queue[idx]
        idx += 1
        with print_lock:
            print(f"\n{CYAN}[Lite] --- Account {idx}/{total} ---{WHITE}")
            print(f"{CYAN}[Lite] Number: {contact[1]}"
                  f"{' (OTP AUTO)' if contact[2] else ''}{WHITE}")

        identity = _gen_identity()
        password = _get_password(password_config)
        if lite_proxies:
            _px = lite_proxies[(idx - 1) % len(lite_proxies)]
            _via = _apply_android_proxy(adb, serial, _px, proxy_state)
            if _via == "settings":
                proxy_state["via_settings"] = True
            with print_lock:
                if _via in ("settings", "emulator"):
                    print(f"{GREEN}[Lite] Proxy applied "
                          f"({_px['host']}:{_px['port']}){WHITE}")
                elif _via == "auth_unsupported" and \
                        not proxy_state["warned"]:
                    proxy_state["warned"] = True
                    print(f"{YELLOW}[Lite] NOTE: auth (password) proxy "
                          f"on a real phone - Android's system proxy "
                          f"does not support passwords, so it cannot "
                          f"be applied here. It applies automatically "
                          f"on an emulator, or whitelist your IP with "
                          f"the provider. Running direct for "
                          f"now.{WHITE}")
        if lite_apks:
            _apk = lite_apks[(idx - 1) % len(lite_apks)]
            if _apk == proxy_state.get("last_apk"):
                with print_lock:
                    print(f"{GREEN}[Lite] Lite version same as the "
                          f"previous account - not reinstalling"
                          f"{WHITE}")
            elif _install_lite_apk(adb, serial, _apk):
                proxy_state["last_apk"] = _apk
                with print_lock:
                    print(f"{GREEN}[Lite] Lite version for this "
                          f"account: {_lite_version_name(adb, serial)} "
                          f"({os.path.basename(_apk)}){WHITE}")
            else:
                with print_lock:
                    print(f"{YELLOW}[Lite] Version install failed "
                          f"({os.path.basename(_apk)}) - continuing "
                          f"with the installed one{WHITE}")
        if ip_refresh_manual:
            with print_lock:
                print(f"{YELLOW}[Lite] Toggle airplane mode ON/OFF "
                      f"on the phone (new IP), then press Enter "
                      f"here{WHITE}")
            input(f"{CYAN}[Lite] Press Enter when ready: {WHITE}")
            if not _wait_device_back(adb):
                with print_lock:
                    print(f"{RED}[Lite] Device did not reconnect - "
                          f"check Wireless debugging{WHITE}")
        result = lite_create_account(adb, serial, identity, password,
                                     contact, counter)

        if result["status"] == "success":
            try:
                # Saved IDs go to the repo folder's output/ - the
                # same place Browser Setup uses, on PC and Termux alike
                output_dir = os.path.join(
                    os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__))), "output")
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

        # Browser Setup rule: a used number is NOT removed
        # from the list (removal exists only in Mode 1 / HTTP)

        if idx < total:
            _reset_lite(adb, serial)
            with print_lock:
                print(f"{CYAN}[Lite] Waiting 45-90s before the "
                      f"next account...{WHITE}")
            _pause(45.0, 90.0)

    with print_lock:
        print(f"{GREEN}[Lite] List finished - all {total} numbers "
              f"processed.{WHITE}")
    if proxy_state.get("via_settings"):
        _clear_android_proxy(adb, serial)
    with print_lock:
        print(f"\n{GREEN}[Lite] Mode finished. Accounts file: "
              f"android_lite_accounts.txt{WHITE}")
