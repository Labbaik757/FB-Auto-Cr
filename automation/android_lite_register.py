"""
FB Auto Create -> Android Setup: Facebook account creation inside
the Facebook Lite ANDROID app (package com.facebook.lite). Selected
from inside Mode 2 (FB Auto Create) in main.py - the mode's original
Browser Setup stays exactly as it was; this is its separate part.

Just like the Browser Setup launches a browser on the PC, this
launches the REAL Lite app on the phone itself:
- On a PC: an emulator or a USB-connected phone (over ADB).
- In Termux (on the phone): the SAME phone - Termux connects to its
  own phone over Wireless ADB (one-time pairing from Developer
  options > Wireless debugging), then launches and drives the Lite
  app installed on that phone. No emulator, no second device.

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
        # Termux (phone par hi): android-tools wala adb
        os.path.join(os.environ.get("PREFIX", ""), "bin", "adb"),
        "/data/data/com.termux/files/usr/bin/adb",
        # Tool ke sath rakhi hui platform-tools
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
    """Kya ye code Termux (Android phone ke andar) chal raha hai?"""
    return "com.termux" in os.environ.get("PREFIX", "")


def _clean_port(text):
    """Port saaf karke do: user poora '192.168.1.5:35907' chipka de
    to sirf aakhri number (35907) nikalta hai; sirf number ho to
    wahi; khali/ghalat ho to khali string."""
    text = (text or "").strip()
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits


def _connect_own_phone(adb):
    """Termux apne hi phone se Wireless ADB jorta hai - taake tool
    USI phone ka asal Facebook Lite app launch/control kar sake
    (bilkul wesay hi jaisay PC par browser launch hota hai).
    Shart: Developer options > Wireless debugging ON (Wi-Fi on ho).
    Pairing sirf pehli dafa hoti hai - code khud guide karta hai."""
    # Pehle se paired ho to aam tareekay se jud jata hai
    try:
        _adb(adb, None, "connect", "localhost:5555", timeout=15)
    except Exception:
        pass
    if _list_devices(adb):
        return True
    with print_lock:
        print(f"\n{YELLOW}[Lite] Ye Termux hai - apne hi phone ke Lite "
              f"app ko launch karne ke liye Wireless ADB jorna hai "
              f"(sirf pehli dafa pairing hoti hai).{WHITE}")
        print(f"{WHITE}[Lite] Phone me ye karo (SIRF EK dafa jana "
              f"hai - teeno cheezein note karke ajao, tool sab ek "
              f"sath pooch lega):{WHITE}")
        print(f"{WHITE}  1. Settings > Developer options > Wireless "
              f"debugging ON karo (Wi-Fi on rakho){WHITE}")
        print(f"{WHITE}  2. Wireless debugging ke andar jao - MAIN "
              f"screen par 'IP address & Port' ke neeche jo number "
              f"hai wo CONNECTION PORT hai, wo note karo{WHITE}")
        print(f"{WHITE}  3. Phir 'Pair device with pairing code' "
              f"dabao - dialog me PAIRING PORT aur 6-digit CODE hai, "
              f"wo bhi note karo{WHITE}")
        print(f"{WHITE}  4. Home dabakar Termux me ajao (Back mat "
              f"dabana - dialog band ho jata hai, lekin note ki hui "
              f"cheezein kaam karengi){WHITE}")
    conn_port = _clean_port(input(f" {GREEN}[{RED}●{GREEN}] "
                                  f"Connection PORT (step 2 wala - "
                                  f"khali choro to tool khud dhund "
                                  f"lega) {EKL} "))
    pair_port = _clean_port(input(f" {GREEN}[{RED}●{GREEN}] Pairing "
                                  f"PORT (dialog wala) {EKL} "))
    pair_code = input(f" {GREEN}[{RED}●{GREEN}] Pairing CODE (6 "
                      f"digits) {EKL} ").strip()
    if pair_port and pair_code:
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
                    print(f"{RED}[Lite] Termux ka adb hi nahi chal "
                          f"raha - use ek package chahiye. Program "
                          f"band karke pehle ye chalao:{WHITE}")
                    print(f"{YELLOW}    pkg install libc++{WHITE}")
                    print(f"{RED}[Lite] Phir dobara chalao - pairing "
                          f"phir se ho jayegi.{WHITE}")
                return False
            if "Successfully paired" not in _out:
                with print_lock:
                    print(f"{RED}[Lite] Pairing nahi hui - PORT aur "
                          f"CODE check karke dobara chalao. (PORT "
                          f"dialog wala number hai, CODE 6-digit "
                          f"wala - dono alag hain.){WHITE}")
                return False
        except Exception as e:
            with print_lock:
                print(f"{RED}[Lite] Pairing error: {e}{WHITE}")
            return False
    # Judna: pehle diya gaya connection port, na mile to phone ki
    # wireless service khud dhundo (mDNS) - user ko dobara Settings
    # me jana hi na pare
    if conn_port:
        try:
            _adb(adb, None, "connect", f"localhost:{conn_port}",
                 timeout=20)
        except Exception:
            pass
    if not _list_devices(adb):
        try:
            res = subprocess.run([adb, "mdns", "services"],
                                 capture_output=True, text=True,
                                 timeout=25)
            _m = re.search(r"_adb-tls-connect\._tcp\s+"
                           r"(\d+\.\d+\.\d+\.\d+:\d+)",
                           (res.stdout or "") + (res.stderr or ""))
            if _m:
                with print_lock:
                    print(f"{CYAN}[Lite] Connection port khud mil "
                          f"gaya: {_m.group(1)}{WHITE}")
                _adb(adb, None, "connect", _m.group(1), timeout=20)
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
    # Pehle maujooda screen par hi dhundo (har screen-parhna phone par
    # 1-3 second leta hai - faltu parhna hi sab se bari susti thi);
    # na mile tabhi intezaar karke dobara parho.
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
    _pause(2.5, 4.0)


def _find_lite_apks():
    """`lite_apks` folder me rakhi hui Facebook Lite ki APK files
    (mukhtalif versions). Har account par in mein se agli version
    install hoti hai - isay kehte hain version rotation: kabhi kisi
    version par account banta hai, kabhi kisi par."""
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
# AUTO SETUP (ek dafa): jo folder/file chahiye code khud banata hai,
# aur Lite ke kuch versions khud rakh leta hai - baar baar nahi.
# ----------------------------------------------------------------------
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
    """Download/pull hui file asal APK hai ya nahi (size + PK magic)."""
    try:
        if os.path.getsize(path) < 1_000_000:
            return False
        with open(path, "rb") as fh:
            return fh.read(2) == b"PK"
    except Exception:
        return False


def _pull_installed_lite_apk(adb, serial, dest_dir):
    """Phone par lagi hui ASAL Lite ka APK nikal kar folder me rakh
    lo - ye sab se mehfooz version hai kyunke ye phone ka apna
    official installed app hai. Filename me version bhi ajata hai."""
    out = _adb(adb, serial, "shell", "pm", "path", LITE_PACKAGE)
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
    """Ek version download karke rakho; nakami par file hata do."""
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
    """Ek-dafa auto setup: (1) lite_apks folder khud banta hai,
    (2) Number_List.txt na ho to khali template ban jata hai,
    (3) output folder tayyar, (4) Lite ke versions: folder me 2 se
    kam hon to phone wali asal Lite nikal kar + downloads try karke
    rakh leta hai. 2+ versions pehle se hon to kuch nahi karta."""
    # 1) lite_apks folder
    dest_dir = None
    for d in _lite_apk_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            if dest_dir is None:
                dest_dir = d
        except Exception:
            continue
    # 2) Number_List.txt template (ho to haath nahi lagta)
    for base in (os.getcwd(),
                 os.path.dirname(os.path.dirname(
                     os.path.abspath(__file__)))):
        _nl = os.path.join(base, "Number_List.txt")
        if os.path.exists(_nl):
            break
        try:
            with open(_nl, "w", encoding="utf-8") as fh:
                fh.write("# Number_List - ek line me ek number\n"
                         "# OTP auto chahiye to number ke sath us ka "
                         "SMS link bhi do:\n"
                         "# +15551234567|https://sms-link.example/xxxx\n"
                         "# Sirf number bhi chalega (code haath se "
                         "likhna hoga):\n"
                         "# +15557654321\n")
            with print_lock:
                print(f"{CYAN}[Lite] Number_List.txt khud bana di hai "
                      f"({_nl}) - numbers is me daal dena{WHITE}")
            break
        except Exception:
            continue
    # 3) Output folder
    try:
        from core.path_manager import get_output_dir
        os.makedirs(get_output_dir(), exist_ok=True)
    except Exception:
        pass
    # 4) Versions - pehle se 2+ hon to bus
    if len(_find_lite_apks()) >= 2 or dest_dir is None:
        return
    with print_lock:
        print(f"{CYAN}[Lite] Lite versions khud rakh raha hoon (ek "
              f"dafa ka kaam hai)...{WHITE}")
    got = []
    if serial:
        pulled = _pull_installed_lite_apk(adb, serial, dest_dir)
        if pulled:
            got.append(pulled)
            with print_lock:
                print(f"{GREEN}[Lite] Phone wali asal Lite rakh li: "
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
            if size in seen:  # wahi file dobara agayi - hata do
                try:
                    os.remove(dest)
                except Exception:
                    pass
                continue
            seen.add(size)
            got.append(dest)
            with print_lock:
                print(f"{GREEN}[Lite] Ek version download karke rakh "
                      f"liya: facebook-lite-{label}.apk{WHITE}")
    total = len(_find_lite_apks())
    with print_lock:
        if total >= 2:
            print(f"{GREEN}[Lite] Ab lite_apks me {total} versions "
                  f"tayyar hain - har account par agli lagegi{WHITE}")
        elif total == 1:
            print(f"{YELLOW}[Lite] Abhi 1 hi version rakhi ja saki - "
                  f"rotation ke liye aur versions is folder me khud "
                  f"bhi daal sakte ho: {dest_dir}{WHITE}")
        else:
            print(f"{YELLOW}[Lite] Koi version auto nahi rakhi ja "
                  f"saki (net/masla) - jo lagi hai usi par chalega. "
                  f"Versions chahiye to APKs is folder me rakho: "
                  f"{dest_dir}{WHITE}")


def _install_lite_apk(adb, serial, apk_path):
    """Ek Lite version install karo (-d = bari version par chhoti
    version lagane ki ijazat, taake rotation har taraf chale)."""
    try:
        res = _adb(adb, serial, "install", "-r", "-d", apk_path,
                   timeout=300)
        blob = (res.stdout or "") + (res.stderr or "")
        return "Success" in blob
    except Exception:
        return False


def _wait_device_back(adb, tries=30):
    """Airplane/Wi-Fi toggle ke baad wireless ADB ke wapas judne
    ka intezaar (maksad 60 second)."""
    for _ in range(tries):
        try:
            _adb(adb, None, "reconnect", timeout=15)
        except Exception:
            pass
        if _list_devices(adb):
            return True
        time.sleep(2)
    return False


_NUMBER_LIST_PATH = None


def _load_number_list():
    """PC wali Number_List.txt parho: har line 'number' ya
    'number|sms_url' / 'number,url' hoti hai (PC wala hi usool).
    [(number, sms_url ya None), ...] wapas milta hai. sms_url wale
    numbers par OTP khud fetch hota hai - yehi PC ka system hai."""
    global _NUMBER_LIST_PATH
    candidates = []
    for base in (os.getcwd(),
                 os.path.dirname(os.path.dirname(
                     os.path.abspath(__file__))),
                 os.path.expanduser("~")):
        candidates.append(os.path.join(base, "Number_List.txt"))
    entries = []
    for path in candidates:
        try:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8",
                      errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    number, url = line, None
                    for sep in ("|", ","):
                        if sep in line:
                            _p = line.split(sep, 1)
                            number, url = _p[0].strip(), _p[1].strip()
                            break
                    if number:
                        entries.append((number, url or None))
            if entries:
                _NUMBER_LIST_PATH = path
                break
        except Exception:
            continue
    return entries


def _remove_number_entry(number, url=None):
    """PC wala usool: jo number istemal ho jaye, wo Number_List.txt
    se hat jata hai. Isi liye dobara run hamesha wahin se shuru
    hota hai jahan pichli dafa ruka tha - na koi ginti ka sawal,
    na number dobara istemal."""
    path = _NUMBER_LIST_PATH
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
        out, removed = [], False
        for line in lines:
            s = line.strip()
            if not removed and s and not s.startswith("#"):
                n, u = s, None
                for sep in ("|", ","):
                    if sep in s:
                        _p = s.split(sep, 1)
                        n, u = _p[0].strip(), _p[1].strip()
                        break
                if n == number and (url is None or u == url):
                    removed = True
                    continue
            out.append(line)
        if removed:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(out)
            remaining = sum(1 for l in out
                            if l.strip() and not l.strip().startswith("#"))
            with print_lock:
                print(f"{CYAN}[Lite] Ye number Number_List se hata "
                      f"diya - {remaining} number bache{WHITE}")
    except Exception:
        pass


# ----------------------------------------------------------------------
# OTP AUTO system - PC (Browser Setup) wala hi logic:
# number ke sath jo SMS link (sms_url) hota hai, code wahan se khud
# fetch hota hai, khud enter hota hai - kuch haath se nahi karna.
# ----------------------------------------------------------------------
def _fetch_otp_from_sms_url(sms_url, timeout=7, interval=1):
    """SMS link se OTP fetch karo (PC wala tareeka, bilkul waisa hi):
    link par GET, jawab plain text hota hai; 'no' se shuru ho to
    matlab code abhi nahi aya; pehla 4-8 digit ka number hi code hai.
    Waqt ke andar baar baar check hota rehta hai."""
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
    """Lite me Resend wala button dabao. Pehle wo option kholo jo
    resend ko chhupata hai ('Didn't get the code' waghera), phir
    resend dabao. PC par ek round me 3 dafa hota hai; mobile par
    zyada resend se 'too many attempts' ajata hai, is liye yahan
    ek round me ek dafa - kul 3 rounds chalte hain."""
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
            print(f"{CYAN}[Lite] Resend dab diya{WHITE}")
        _pause(1.2, 2.2)
        return True
    return False


def _auto_otp_rounds(adb, serial, sms_url):
    """PC wala resend+fetch chakkar: 3 rounds, har round me resend
    dabao phir ~7 second link check karo. Code mile to wapas do."""
    with print_lock:
        print(f"{CYAN}[Lite] OTP auto-fetch ho raha hai SMS link "
              f"se...{WHITE}")
    for _round in range(3):
        _tap_resend_in_lite(adb, serial)
        code = _fetch_otp_from_sms_url(sms_url, timeout=7, interval=1)
        if code:
            with print_lock:
                print(f"{GREEN}[Lite] OTP mil gaya: {code}{WHITE}")
            return code
        if _round < 2:
            with print_lock:
                print(f"{YELLOW}[Lite] OTP abhi nahi aya, dobara "
                      f"resend... ({_round + 2}/3){WHITE}")
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
            _log_screen(nodes, "Create account wala button nahi mila")
            return _fail("no_create_button")
        _tap_text(adb, serial, nodes, TEXTS["create_account"])
        _pause(1.2, 2.2)

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
        _pause(1.2, 2.2)

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
        _pause(1.2, 2.2)

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
                _log_screen(nodes, "Facebook ne confirmation/block screen "
                                   "dikhaya hai")
                if counter:
                    counter.update("success")
                return {"status": "success",
                        "reason": "profile_verification_pending",
                        "result_line": result_line + "|pending"}
            if _screen_has(nodes, TEXTS["code_prompt"]):
                # PC wala system: SMS link ho to OTP KHUD fetch aur
                # enter hota hai; na mile to aakhir me haath se mauqa
                code = None
                if sms_url:
                    code = _auto_otp_rounds(adb, serial, sms_url)
                else:
                    _tap_resend_in_lite(adb, serial)
                if not code:
                    with print_lock:
                        print(f"{YELLOW}[Lite] Auto OTP nahi mila - "
                              f"{address} par aya code yahan likho "
                              f"(khali = skip){WHITE}")
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
                    "Aakhri screen wazeh nahi - pending save ho raha hai")
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


def run_android_lite_mode(password_config, counter=None):
    """Facebook Lite app me accounts banao - Browser Setup wala
    usool: koi ginti ka sawal nahi; Number_List / saved emails me
    jitne hain utne hi accounts bante hain, list khatam = mode
    khatam. Haath se likhne par khali Enter = khatam."""
    with print_lock:
        print(f"\n{CYAN}[Lite] === FB Lite Android Mode (Facebook Lite "
              f"app only) ==={WHITE}")

    adb = _find_adb()
    if not adb:
        with print_lock:
            if _is_termux():
                print(f"{RED}[Lite] adb nahi mila! Termux me pehle ye "
                      f"chalao: pkg install android-tools - phir dobara "
                      f"try karo.{WHITE}")
            else:
                print(f"{RED}[Lite] adb nahi mila! Android SDK "
                      f"platform-tools install karo (ya apne Android "
                      f"Emulator Launcher se ek device banao - usi SDK "
                      f"me adb hota hai), phir dobara try karo.{WHITE}")
        return

    devices = _list_devices(adb)
    if not devices and _is_termux():
        # Termux apne hi phone par hai: Wireless ADB se khud ko joro,
        # taake isi phone ka asal Lite app launch ho
        if _connect_own_phone(adb):
            devices = _list_devices(adb)
    if not devices:
        with print_lock:
            if _is_termux():
                print(f"{RED}[Lite] Phone se ADB nahi jura. Wireless "
                      f"debugging ON hai aur pairing sahi hui thi? "
                      f"Phir se try karo.{WHITE}")
            else:
                print(f"{RED}[Lite] Koi Android device/emulator "
                      f"connected nahi hai. Pehle emulator launch karo "
                      f"(apne launcher se) ya phone USB debugging ON "
                      f"karke lagao, phir dobara try karo.{WHITE}")
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
        _auto_apks = _find_lite_apks()
        if _auto_apks:
            with print_lock:
                print(f"{CYAN}[Lite] lite_apks folder se pehli version "
                      f"install ho rahi hai...{WHITE}")
            _install_lite_apk(adb, serial, _auto_apks[0])
        apk = ""
        if not _lite_installed(adb, serial):
            apk = input(f" {GREEN}[{RED}●{GREEN}] Lite APK ka full path "
                        f"(khali = Play Store se khud install karke "
                        f"dobara chalao) {EKL} ").strip().strip('"')
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
        print(f"{GREEN}[Lite] Facebook Lite tayyar hai "
              f"(version {_lite_version_name(adb, serial)}){WHITE}")

    # Ek-dafa auto setup: folders/files khud bante hain, Lite ke
    # versions khud rakh liye jate hain (2+ hon to kuch nahi hota)
    _ensure_lite_setup(adb, serial)

    # Version rotation ke liye APKs (agar lite_apks folder maujood ho)
    lite_apks = _find_lite_apks()
    if lite_apks:
        with print_lock:
            print(f"{GREEN}[Lite] lite_apks folder me {len(lite_apks)} "
                  f"versions mile - har account par agli version "
                  f"lagegi{WHITE}")

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

    # Bina proxy ke, mobile data par: har account se pehle khud
    # airplane mode on/off karke naya IP lene ka option (linking se
    # bachne ke liye IP badalna sab se ahem hai)
    ip_refresh_manual = False
    if not lite_proxies:
        try:
            _ans2 = input(f" {GREEN}[{RED}●{GREEN}] Har account se "
                          f"pehle khud airplane mode ON/OFF karke naya "
                          f"IP lena hai? (sirf mobile data ke liye) "
                          f"(y/n) [n] {EKL} ").strip().lower()
        except Exception:
            _ans2 = "n"
        ip_refresh_manual = (_ans2 == "y")

    # Contact choice: saved Outlook emails, typed emails, or phone numbers
    saved_emails = _load_saved_emails()
    number_entries = _load_number_list()
    menu = []
    if number_entries:
        _with_url = sum(1 for _n, _u in number_entries if _u)
        menu.append(("numbers",
                     f"Mobile numbers - Number_List.txt se "
                     f"({len(number_entries)} mile; {_with_url} ke sath "
                     f"SMS link hai = un par OTP AUTO ayega)"))
    if saved_emails:
        menu.append(("saved",
                     f"Email - saved Outlook accounts se "
                     f"({len(saved_emails)} mile)"))
    menu.append(("email", "Email - har account ke liye khud likhunga"))
    menu.append(("phone", "Mobile number - har account ke liye khud "
                          "likhunga (SMS link nahi, code haath se)"))
    with print_lock:
        for _mi, (_mk, _mlabel) in enumerate(menu, 1):
            print(f" {GREEN}[{RED}0{_mi}{GREEN}] {_mlabel}{WHITE}")
    _pick = input(f" {GREEN}[{RED}●{GREEN}] Select (1-{len(menu)}) [1] "
                  f"{EKL} ").strip() or "1"
    try:
        src = menu[int(_pick) - 1][0]
    except Exception:
        src = menu[0][0]

    # Browser Setup wala usool: koi "how many accounts" ka sawal
    # nahi. File wale sources (Number_List / saved emails) me jitne
    # hain utne hi accounts bante hain - tool khud pehle se aakhir
    # tak jata hai aur list khatam hote hi ruk jata hai.
    queue = []
    if src == "numbers":
        queue = [("phone", _n, _u) for (_n, _u) in number_entries]
    elif src == "saved":
        queue = [("email", _e) for _e in saved_emails]
    total = len(queue)

    from core.counter import Counter
    if counter is None:
        counter = Counter()

    idx = 0
    while True:
        if queue:
            if idx >= total:
                with print_lock:
                    print(f"{GREEN}[Lite] List khatam - kul {total} "
                          f"the, sab ho gaye.{WHITE}")
                break
            contact = queue[idx]
            idx += 1
            with print_lock:
                print(f"\n{CYAN}[Lite] --- Account {idx}/{total} ---{WHITE}")
                if contact[0] == "phone":
                    print(f"{CYAN}[Lite] Number: {contact[1]}"
                          f"{' (OTP AUTO)' if contact[2] else ''}{WHITE}")
        else:
            # Haath se likhne wala source: har dafa poochta hai,
            # khali Enter = mode khatam (rukna tumhare haath me)
            _lbl = "email" if src == "email" else "mobile number"
            address = input(f" {GREEN}[{RED}●{GREEN}] Is account ke "
                            f"liye {_lbl} (khali = khatam) {EKL} ").strip()
            if not address:
                with print_lock:
                    print(f"{GREEN}[Lite] Theek hai - mode khatam ho "
                          f"raha hai.{WHITE}")
                break
            idx += 1
            contact = (("email", address) if src == "email"
                       else ("phone", address))
            with print_lock:
                print(f"\n{CYAN}[Lite] --- Account {idx} ---{WHITE}")
            if idx > 1:
                _reset_lite(adb, serial)
                with print_lock:
                    print(f"{CYAN}[Lite] Agla account 45-90 second "
                          f"baad - jaldi jaldi accounts banana hi "
                          f"sab se bara khatra hai{WHITE}")
                _pause(45.0, 90.0)

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
        if lite_apks:
            _apk = lite_apks[(idx - 1) % len(lite_apks)]
            if _apk == proxy_state.get("last_apk"):
                with print_lock:
                    print(f"{GREEN}[Lite] Lite version wahi hai jo "
                          f"pichle account par thi - dobara install "
                          f"nahi ho rahi{WHITE}")
            elif _install_lite_apk(adb, serial, _apk):
                proxy_state["last_apk"] = _apk
                with print_lock:
                    print(f"{GREEN}[Lite] Is account ke liye Lite "
                          f"version: {_lite_version_name(adb, serial)} "
                          f"({os.path.basename(_apk)}){WHITE}")
            else:
                with print_lock:
                    print(f"{YELLOW}[Lite] Version install nahi hui "
                          f"({os.path.basename(_apk)}) - jo lagi hai "
                          f"usi par chalega{WHITE}")
        if ip_refresh_manual:
            with print_lock:
                print(f"{YELLOW}[Lite] Ab phone me Airplane mode ON "
                      f"karke OFF kar do (naya IP milega), phir yahan "
                      f"Enter dabao{WHITE}")
            input(f"{CYAN}[Lite] Tayyar ho to Enter: {WHITE}")
            if not _wait_device_back(adb):
                with print_lock:
                    print(f"{RED}[Lite] Device wapas nahi jura - "
                          f"Wireless debugging check karo{WHITE}")
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

        # PC wala usool: istemal shuda number list se hat jata hai
        if src == "numbers":
            _remove_number_entry(
                contact[1], contact[2] if len(contact) > 2 else None)

        if queue and idx < total:
            _reset_lite(adb, serial)
            with print_lock:
                print(f"{CYAN}[Lite] Agla account 45-90 second baad - "
                      f"jaldi jaldi accounts banana hi sab se bara "
                      f"khatra hai{WHITE}")
            _pause(45.0, 90.0)

    if proxy_state.get("via_settings"):
        _clear_android_proxy(adb, serial)
    with print_lock:
        print(f"\n{GREEN}[Lite] Mode khatam. Accounts file: "
              f"android_lite_accounts.txt{WHITE}")
