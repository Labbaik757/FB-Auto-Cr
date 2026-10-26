"""DP image generation via the Pollinations free image API (TEST VERSION).

Plain HTTP, stdlib only. No key is required: anonymous calls work on
this endpoint. If POLLINATIONS_API_KEY is set it is sent with requests;
it is never stored in the repo.
"""

import random
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://image.pollinations.ai"
MODEL = "flux"
WIDTH = 1024
HEIGHT = 1024

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

_BACKGROUNDS = [
    "plain light grey studio background",
    "soft outdoor park background, blurred",
    "neutral indoor wall background",
    "city street background, blurred",
    "plain beige studio background",
]
_CLOTHING = [
    "casual t-shirt",
    "smart casual shirt",
    "simple kurta",
    "casual jacket over a t-shirt",
    "plain polo shirt",
]
_POSES = [
    "facing the camera, slight smile",
    "facing the camera, neutral expression",
    "slight three-quarter angle, relaxed smile",
    "facing the camera, friendly expression",
]


def build_prompt(name, gender, seed):
    """Photorealistic square profile-portrait prompt for one account.

    gender: 'male' | 'female' | anything else = neutral wording.
    seed: int; picks background/clothing/pose deterministically so every
    account's DP differs from the others. The name is not embedded in
    the prompt; it is only used for logging.
    """
    rng = random.Random(seed)
    g = (gender or "").strip().lower()
    if g in ("male", "m"):
        subject = "photorealistic portrait of a young adult man"
    elif g in ("female", "f"):
        subject = "photorealistic portrait of a young adult woman"
    else:
        subject = "photorealistic portrait of a young adult person"
    return (
        f"{subject}, head and shoulders, square profile photo, "
        f"{rng.choice(_POSES)}, wearing a {rng.choice(_CLOTHING)}, "
        f"{rng.choice(_BACKGROUNDS)}, natural daylight, sharp focus, "
        f"realistic skin texture, no text, no watermark"
    )


def generate_png(prompt, out_path, seed=1, api_key=None, timeout=120,
                 base_url=BASE_URL, max_attempts=3):
    """Fetch one image. Returns dict(ok, path, bytes, attempts, error).

    Retries on HTTP 5xx / timeouts. Rejects non-image bodies (HTML error
    pages) instead of saving them as a fake PNG.
    """
                     q = urllib.parse.quote(prompt)
    url = (f"{base_url}/prompt/{q}"
           f"?model={MODEL}&width={WIDTH}&height={HEIGHT}&seed={seed}&nologo=true")
    headers = {"User-Agent": "fb-auto-cr-dp/1.0"}
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if data.startswith(PNG_MAGIC):
                ext = ".png"
            elif data.startswith(JPEG_MAGIC):
                ext = ".jpg"
            else:
                return {"ok": False, "path": None, "bytes": 0,
                        "attempts": attempt,
                        "error": "response was not an image (error page?)"}
            path = out_path if out_path.endswith(ext) else out_path + ext
            with open(path, "wb") as f:
                f.write(data)
            return {"ok": True, "path": path, "bytes": len(data),
                    "attempts": attempt, "error": ""}
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
            if e.code < 500:
                break
        except Exception as e:  # timeout, DNS, connection reset
            last_error = f"{type(e).__name__}: {e}"
        time.sleep(2)
    return {"ok": False, "path": None, "bytes": 0,
            "attempts": max_attempts, "error": last_error}
