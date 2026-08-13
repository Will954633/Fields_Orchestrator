"""Shared configuration for the ID4ME automation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Dedicated Chrome profile. Logged in once via `python id4me_bot.py login`,
# the session cookies live here and survive across runs and reboots.
PROFILE_DIR = ROOT / ".chrome_profile"

OUTPUT_DIR = ROOT / "output"
DISCOVERY_DIR = ROOT / "discovery"
SELECTORS_FILE = ROOT / "selectors.json"

BASE_URL = "https://id4me.me"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

# Chrome channel: use the real installed Chrome rather than bundled Chromium so
# the browser fingerprint matches an ordinary human session.
CHROME_CHANNEL = "chrome"

DEFAULT_TIMEOUT_MS = 45_000
# Politeness delay between addresses in a batch run (seconds).
BATCH_DELAY_SECONDS = 3.0

for _d in (OUTPUT_DIR, DISCOVERY_DIR):
    _d.mkdir(parents=True, exist_ok=True)
