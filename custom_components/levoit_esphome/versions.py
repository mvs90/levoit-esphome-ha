"""Component versions: what a device reports, what a channel offers.

Plain functions without Home Assistant state, so they are easy to test.

A device reports its component version through the `esp_version` text sensor:

    1.7.0 esphome                 built without git, or 1.7.0 and older
    1.7.0+3fa21c4 esphome         built from commit 3fa21c4
    1.7.0+3fa21c4.dirty esphome   local checkout with uncommitted changes
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from awesomeversion import AwesomeVersion, AwesomeVersionException

from .const import (
    CHANNEL_LOCAL,
    CHANNEL_MAIN,
    CHANNEL_PINNED,
    CHANNEL_STABLE,
    COMPONENTS,
    GITHUB_REPO,
)

_REPORTED = re.compile(
    r"^(?P<release>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)"
    r"(?:\+(?P<commit>[0-9a-f]{7,40})(?P<dirty>\.dirty)?)?"
    # always there (every release since 1.1.0); it is what tells the ESP
    # version apart from the MCU version sensor, e.g. "1.0.2"
    r" esphome$"
)


@dataclass(frozen=True)
class Reported:
    """The component version a device runs."""

    release: str
    commit: str | None = None
    dirty: bool = False

    @property
    def text(self) -> str:
        """Version as shown in Home Assistant, e.g. 1.7.0+3fa21c4."""
        if self.commit is None:
            return self.release
        return f"{self.release}+{self.commit}{'.dirty' if self.dirty else ''}"


@dataclass(frozen=True)
class ChannelHead:
    """The newest component version on a channel."""

    release: str
    commit: str
    notes: str | None = None
    url: str | None = None

    @property
    def text(self) -> str:
        """Version as shown in Home Assistant, e.g. 1.8.0+3fa21c4."""
        return f"{self.release}+{self.commit}"


def parse_reported(state: str | None) -> Reported | None:
    """Parse an `esp_version` sensor state; None if it is not one."""
    if not state:
        return None
    match = _REPORTED.match(state.strip())
    if match is None:
        return None
    commit = match.group("commit")
    return Reported(
        release=match.group("release"),
        commit=commit[:7] if commit else None,
        dirty=match.group("dirty") is not None,
    )


def _release_newer(latest: str, installed: str) -> bool:
    try:
        return AwesomeVersion(latest) > AwesomeVersion(installed)
    except AwesomeVersionException:
        return False


def is_behind(reported: Reported, head: ChannelHead, channel: str) -> bool:
    """Whether the channel has something newer than the device runs.

    * `stable`: only a newer release counts. A device that runs another commit
      of the same release (built from `main` after it) is not behind.
    * `main`: the commits decide where both sides have one; the head of main
      is the newest there is. Without a commit (1.7.0 and older, or no git)
      only the release number can be compared.
    * A `.dirty` local build is never offered an update: it is on no channel.
    """
    if reported.dirty:
        return False
    if channel == CHANNEL_MAIN and reported.commit:
        return not (
            head.commit.startswith(reported.commit) or reported.commit.startswith(head.commit)
        )
    return _release_newer(head.release, reported.release)


def channel_from_ref(ref: str | None) -> str:
    """Map the component's git ref to a channel."""
    if ref in (None, "", CHANNEL_MAIN):
        # external_components without a ref builds the default branch, main
        return CHANNEL_MAIN
    if ref == CHANNEL_STABLE:
        return CHANNEL_STABLE
    return CHANNEL_PINNED


def _is_our_repo(url: str) -> bool:
    url = url.lower().removesuffix(".git").rstrip("/")
    return url.endswith(f"github.com/{GITHUB_REPO}") or url == GITHUB_REPO


def component_source(config: dict[str, Any]) -> tuple[str, str | None] | None:
    """Channel and ref of the levoit / philips source in a resolved config.

    Returns (channel, ref), or None if the config does not pull either
    component through external_components.
    """
    for entry in config.get("external_components") or []:
        if not isinstance(entry, dict):
            continue
        components = entry.get("components")
        if isinstance(components, list) and not COMPONENTS & set(components):
            continue
        source = entry.get("source")
        if isinstance(source, str):
            # shorthand: github://tuct/levoit[@ref]
            if not source.startswith("github://"):
                continue
            repo, _, ref = source.removeprefix("github://").partition("@")
            if not _is_our_repo(repo):
                return CHANNEL_PINNED, ref or None
            return channel_from_ref(ref or None), ref or None
        if isinstance(source, dict):
            if source.get("type") == "local":
                return CHANNEL_LOCAL, None
            if source.get("type") == "git":
                ref = source.get("ref")
                if not _is_our_repo(str(source.get("url", ""))):
                    return CHANNEL_PINNED, ref
                return channel_from_ref(ref), ref
    return None


def component_model(config: dict[str, Any]) -> str | None:
    """`model:` of the levoit or philips block in a resolved config."""
    for component in sorted(COMPONENTS):
        block = config.get(component)
        if isinstance(block, list):
            block = block[0] if block else None
        if isinstance(block, dict) and block.get("model"):
            return str(block["model"])
    return None
