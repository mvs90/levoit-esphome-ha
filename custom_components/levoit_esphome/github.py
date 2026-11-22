"""Newest component version per channel, from GitHub."""

from __future__ import annotations

import aiohttp

from .const import (
    CHANNEL_MAIN,
    CHANNEL_STABLE,
    GITHUB_API,
    GITHUB_RAW,
    GITHUB_REPO,
    VERSION_FILE,
)
from .versions import ChannelHead

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "levoit-esphome-ha"}


async def _json(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url, headers=_HEADERS, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _text(session: aiohttp.ClientSession, url: str, accept: str) -> str:
    headers = {**_HEADERS, "Accept": accept}
    async with session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        return (await resp.text()).strip()


async def async_fetch_heads(session: aiohttp.ClientSession) -> dict[str, ChannelHead]:
    """The head of `stable` (latest release) and of `main`.

    Four requests; raises aiohttp.ClientError on failure.
    """
    release = await _json(session, f"{GITHUB_API}/releases/latest")
    stable_sha = await _text(
        session, f"{GITHUB_API}/commits/{CHANNEL_STABLE}", "application/vnd.github.sha"
    )
    main_sha = await _text(
        session, f"{GITHUB_API}/commits/{CHANNEL_MAIN}", "application/vnd.github.sha"
    )
    main_version = await _text(session, f"{GITHUB_RAW}/{CHANNEL_MAIN}/{VERSION_FILE}", "text/plain")
    return {
        CHANNEL_STABLE: ChannelHead(
            release=str(release["tag_name"]),
            commit=stable_sha[:7],
            notes=release.get("body") or None,
            url=release.get("html_url"),
        ),
        CHANNEL_MAIN: ChannelHead(
            release=main_version,
            commit=main_sha[:7],
            notes=None,
            url=f"https://github.com/{GITHUB_REPO}/commits/{CHANNEL_MAIN}",
        ),
    }
