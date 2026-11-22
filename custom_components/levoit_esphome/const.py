"""Constants for Levoit ESPHome."""

from datetime import timedelta

DOMAIN = "levoit_esphome"

# ESPHome components from tuct/levoit that make a device ours.
COMPONENTS = frozenset({"levoit", "philips"})

GITHUB_REPO = "tuct/levoit"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}"
VERSION_FILE = "components/levoit/VERSION"

CHANNEL_STABLE = "stable"
CHANNEL_MAIN = "main"
# A ref that is neither: a tag, a fork, a local path. No updates offered.
CHANNEL_PINNED = "pinned"
CHANNEL_LOCAL = "local"

# Device Builder device list and Home Assistant states.
SCAN_INTERVAL = timedelta(minutes=5)
# Releases and branch heads on GitHub (unauthenticated API: 60 requests/hour).
GITHUB_INTERVAL = timedelta(hours=6)
# Model and channel read from each config. Every read runs `esphome config` in
# the Device Builder, so it is cached.
CONFIG_INTERVAL = timedelta(hours=6)
