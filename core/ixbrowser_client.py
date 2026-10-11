"""
ixBrowser Local API client wrapper.

Uses the official `ixbrowser-local-api` Python package to control
ixBrowser profiles via its local API (default http://127.0.0.1:53200).

Each Facebook account gets a FRESH profile with a RANDOM fingerprint,
so every signup looks like a different device.

Requires:
    pip install ixbrowser-local-api
    ixBrowser desktop client installed, running, with Local API enabled.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from ixbrowser_local_api import IXBrowserClient
    IXBROWSER_AVAILABLE = True
except ImportError:
    IXBrowserClient = None
    IXBROWSER_AVAILABLE = False

from ui.colors import GREEN, RED, WHITE, YELLOW, CYAN


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ixbrowser.json",
)


def load_ix_config():
    """Load ixBrowser settings from ixbrowser.json (created on first run)."""
    defaults = {
        "target": "127.0.0.1",
        "port": 53200,
        "profile_group": "",
        "delete_profile_after": False,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            defaults.update(data)
        except Exception:
            pass
    else:
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(defaults, f, indent=2)
        except Exception:
            pass
    return defaults


class IxBrowser:
    """Thin wrapper around the official ixBrowser local API client."""

    def __init__(self, target="127.0.0.1", port=53200):
        if not IXBROWSER_AVAILABLE:
            raise RuntimeError(
                "ixbrowser-local-api not installed. Run: pip install ixbrowser-local-api"
            )
        self.client = IXBrowserClient(target=target, port=port)
        self.target = target
        self.port = port

    def _check(self, result, action):
        if result is None:
            raise RuntimeError(
                f"ixBrowser {action} failed: [{self.client.code}] {self.client.message}"
            )
        return result

    def create_fresh_profile(self, name):
        """Create a new profile with a randomized fingerprint. Returns profile_id."""
        from ixbrowser_local_api import Profile

        profile = Profile()
        profile.name = name
        profile.randomColor()
        # Randomize fingerprint at creation
        result = self._check(
            self.client.create_profile(profile), "create_profile"
        )
        # API returns profile info; extract profile_id
        if isinstance(result, dict):
            return result.get("profile_id") or result.get("id")
        return result

    def open_with_random_fingerprint(self, profile_id):
        """
        Open profile with a randomized fingerprint.
        Returns (debugging_address, webdriver_url).
        """
        result = self._check(
            self.client.open_profile_with_random_fingerprint(
                profile_id,
                cookies_backup=False,
                load_profile_info_page=False,
            ),
            "open_profile_with_random_fingerprint",
        )
        debugging_address = result.get("debugging_address")
        webdriver_url = result.get("webdriver")
        if not debugging_address:
            raise RuntimeError(
                f"ixBrowser did not return debugging_address: {result}"
            )
        return debugging_address, webdriver_url

    def close_profile(self, profile_id):
        """Close an opened profile."""
        return self._check(
            self.client.close_profile(profile_id), "close_profile"
        )

    def delete_profile(self, profile_id):
        """Delete a profile (used when delete_profile_after is True)."""
        return self._check(
            self.client.delete_profile(profile_id), "delete_profile"
        )

    def ping(self):
        """Check that the local API is reachable."""
        result = self.client.get_profile_list()
        if result is None:
            raise RuntimeError(
                f"Cannot reach ixBrowser API at {self.target}:{self.port}. "
                f"[{self.client.code}] {self.client.message} "
                "(Is the ixBrowser client running with Local API enabled?)"
            )
        return True


def get_ixbrowser():
    """Build an IxBrowser instance from ixbrowser.json settings."""
    cfg = load_ix_config()
    return IxBrowser(target=cfg.get("target", "127.0.0.1"),
                     port=cfg.get("port", 53200)), cfg
