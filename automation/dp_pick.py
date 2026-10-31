"""DP picker (TEST VERSION) - DP pictures come from FILES, not AI.

No generation of any kind lives here: no Gemini, no Pollinations,
no image model. The account's picture is picked from a folder of
photos the user keeps in the project:

    dp_pics/
        male/      <- photos of men
        female/    <- photos of women
        README.md

How a picture is picked for one account (correct logic, no guessing):
  1. Gender: read from the profile's About page ("Gender: Female /
     Male") when it is visible there; otherwise the account's first
     name is looked up in a small built-in first-name list. If
     neither works, gender is unknown.
  2. Name: the display name is read from the profile after login.
     A file whose name matches the full name (e.g.
     "Sophia Wilson.jpg") or the first name wins.
  3. Pick order inside the gender folder: exact full-name match,
     then first-name match, then any picture not used before. A
     named match is used even if the file was used before (same
     person, same picture is correct). If every picture in the
     folder was already used, the first one is reused and the log
     says so.
  4. Gender unknown + no named picture in either folder -> no
     picture is picked (the account is skipped honestly). A
     wrong-gender DP is never applied.
"""

import os
import re

from core.path_manager import get_output_dir

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# Common first names, for the gender fallback only (used only when
# the About page does not show a gender). Kept small on purpose:
# an unknown name means "unknown gender", never a guess.
FEMALE_FIRST_NAMES = {
    "sophia", "dayana", "isabella", "kristen", "erin", "jennifer",
    "melanie", "rebecca", "sarah", "ashley", "lynn", "lisa",
    "sandra", "emma", "olivia", "ava", "mia", "amelia", "harper",
    "evelyn", "abigail", "ella", "scarlett", "grace", "chloe",
    "victoria", "riley", "aria", "lily", "aubrey", "zoey", "penelope",
    "layla", "nora", "camila", "hannah", "samantha", "anna",
    "natalie", "leah", "zoe", "stella", "hazel", "violet", "aurora",
    "savannah", "audrey", "brooklyn", "bella", "claire", "skylar",
    "lucy", "paisley", "everly", "anna", "caroline", "nova",
    "genesis", "emilia", "kennedy", "samantha", "maya", "willow",
    "kinsley", "naomi", "elena", "sara", "ariel", "allison",
    "rachel", "lauren", "megan", "nicole", "jessica", "amanda",
    "stephanie", "michelle", "kimberly", "elizabeth", "ashley",
    "emily", "courtney", "danielle", "brittany", "melissa",
}

MALE_FIRST_NAMES = {
    "joseph", "sean", "michael", "erik", "jonathan", "robert",
    "cameron", "scott", "brian", "james", "john", "robert", "david",
    "william", "richard", "charles", "thomas", "donald", "ronald",
    "paul", "mark", "george", "kenneth", "steven", "edward",
    "brian", "kevin", "jason", "jeffrey", "ryan", "jacob", "gary",
    "nicholas", "eric", "jonathan", "stephen", "larry", "justin",
    "scott", "brandon", "benjamin", "samuel", "raymond", "gregory",
    "frank", "alexander", "patrick", "jack", "dennis", "jerry",
    "tyler", "aaron", "jose", "nathan", "adam", "henry", "douglas",
    "zachary", "kyle", "noah", "ethan", "jeremy", "harold",
    "keith", "christian", "roger", "noah", "gerald", "carl",
    "terry", "sean", "austin", "arthur", "lawrence", "jesse",
    "jordan", "bryan", "billy", "bruce", "albert", "gabriel",
    "logan", "alan", "juan", "wayne", "ralph", "roy", "eugene",
    "randy", "vincent", "russell", "elijah", "louis", "bobby",
    "philip", "johnny", "anthony", "andrew", "joshua", "daniel",
    "matthew", "christopher", "william", "christopher", "anthony",
}


def project_root():
    """Project root = folder containing automation/."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dp_pics_dir():
    return os.path.join(project_root(), "dp_pics")


def used_file_path():
    return os.path.join(get_output_dir(), "used_dp_pics.txt")


def _norm(s):
    """Lowercase, non-alphanumeric runs become one space."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _list_pics(folder):
    pics = []
    try:
        names = sorted(os.listdir(folder))
    except Exception:
        return pics
    for name in names:
        path = os.path.join(folder, name)
        try:
            if (os.path.isfile(path)
                    and name.lower().endswith(IMAGE_EXTS)
                    and os.path.getsize(path) > 0):
                pics.append(path)
        except Exception:
            continue
    return pics


def folder_status(pics_dir=None):
    """Pic counts per gender folder, for the run header."""
    base = pics_dir or dp_pics_dir()
    return {
        "male": len(_list_pics(os.path.join(base, "male"))),
        "female": len(_list_pics(os.path.join(base, "female"))),
    }


def gender_from_name(name):
    """First-name lookup only. '' = unknown, never a guess."""
    first = _norm(name).split(" ")[0] if _norm(name) else ""
    if first in FEMALE_FIRST_NAMES:
        return "female"
    if first in MALE_FIRST_NAMES:
        return "male"
    return ""


def detect_gender(page, uid, name):
    """Read the account's gender. Returns (gender, method):
    method is 'about' (About page showed it), 'first-name' (the
    first-name list), or 'unknown'. Never raises, never guesses."""
    try:
        page.goto(
            "https://www.facebook.com/profile.php?id={}&"
            "sk=about_contact_and_basic_info".format(uid),
            wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_timeout(3000)
        except Exception:
            pass
        try:
            text = page.evaluate(
                "() => document.body.innerText || ''")
        except Exception:
            text = ""
        flat = " ".join((text or "").lower().split())
        m = re.search(r"gender\s*[:\-]?\s*(female|male)\b", flat)
        if m:
            return m.group(1), "about"
    except Exception:
        pass
    g = gender_from_name(name)
    if g:
        return g, "first-name"
    return "", "unknown"


def _load_used(used_path):
    used = set()
    try:
        with open(used_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    used.add(line)
    except Exception:
        pass
    return used


def record_used(used_path, pic_path):
    """Remember a picture was used (failures never kill the run)."""
    try:
        os.makedirs(os.path.dirname(used_path), exist_ok=True)
        with open(used_path, "a", encoding="utf-8") as f:
            f.write(pic_path + "\n")
    except Exception:
        pass


def pick_dp(name, gender, used_path=None, pics_dir=None):
    """Pick one picture file for this account.
    Returns {"path", "reason", "gender"} or None (no honest pick).
    gender "" means unknown: only a named picture counts, never a
    random one from either folder."""
    base = pics_dir or dp_pics_dir()
    full = _norm(name)
    first = full.split(" ")[0] if full else ""
    used = _load_used(used_path or used_file_path())
    folders = []
    if gender in ("male", "female"):
        folders = [gender]
    else:
        folders = ["female", "male"]
    best = None  # (score, unused, path, reason)
    for folder in folders:
        for path in _list_pics(os.path.join(base, folder)):
            stem = _norm(os.path.splitext(os.path.basename(path))[0])
            if full and stem == full:
                score, reason = 3, "name match"
            elif first and (stem == first or stem.startswith(first + " ")
                            or (" " + first + " ") in (" " + stem + " ")):
                score, reason = 2, "first-name match"
            elif gender:
                score, reason = 1, "unused pic"
            else:
                continue  # unknown gender: named pics only
            unused = path not in used
            key = (score, 1 if unused else 0)
            if best is None or key > best[0]:
                best = (key, path, reason, unused)
    if best is None:
        return None
    _, path, reason, unused = best
    if not unused and reason == "unused pic":
        reason = "reused pic (all used)"
    return {"path": path, "reason": reason, "gender": gender}
