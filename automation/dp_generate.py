"""DP image generation via the Pollinations free image API (TEST VERSION).

Plain HTTP, stdlib only. Dual endpoint, per Pollinations' own setup:
key set -> keyed gen endpoint (/image/) with Bearer auth; no key ->
anonymous legacy endpoint (/prompt/, shared pool, may hit limits).
The key comes only from POLLINATIONS_API_KEY, never from the repo.
"""

import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://image.pollinations.ai"
GEN_URL = "https://gen.pollinations.ai"
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


def _image_url(prompt, seed, api_key, base_url=None):
    """Keyed: gen endpoint (/image/). Anonymous: legacy (/prompt/)."""
    q = urllib.parse.quote(prompt)
    if api_key:
        host = base_url or GEN_URL
        return (f"{host}/image/{q}"
                f"?model={MODEL}&width={WIDTH}&height={HEIGHT}&seed={seed}")
    host = base_url or BASE_URL
    return (f"{host}/prompt/{q}"
            f"?model={MODEL}&width={WIDTH}&height={HEIGHT}&seed={seed}&nologo=true")


def generate_png(prompt, out_path, seed=1, api_key=None, timeout=120,
                 base_url=None, max_attempts=3):
    """Fetch one image. Returns dict(ok, path, bytes, attempts, error).

    Retries on HTTP 5xx / timeouts. Rejects non-image bodies (HTML error
    pages) instead of saving them as a fake PNG.
    """
    url = _image_url(prompt, seed, api_key, base_url)
    headers = {"User-Agent": "fb-auto-cr-dp/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error = ""
    last_attempt = 0
    for attempt in range(1, max_attempts + 1):
        last_attempt = attempt
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
            try:
                body = e.read().decode("utf-8", "replace").strip()[:200]
            except Exception:
                body = ""
            last_error = f"HTTP {e.code}" + (f": {body}" if body else "")
            if e.code == 503:
                # Shared free pool at its limit: the service itself says
                # when to retry. Honour it instead of hammering.
                time.sleep(_retry_after_seconds(body))
                continue
            if e.code < 500:
                break
        except Exception as e:  # timeout, DNS, connection reset
            last_error = f"{type(e).__name__}: {e}"
        time.sleep(2)
    return {"ok": False, "path": None, "bytes": 0,
            "attempts": last_attempt, "error": last_error}


def _retry_after_seconds(body):
    """Seconds from a 'Retry after Ns' message, else the 10s default."""
    m = re.search(r"retry after (\d+)\s*s", body or "", re.I)
    return int(m.group(1)) if m else 10
