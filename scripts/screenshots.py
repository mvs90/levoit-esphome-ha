"""Take the README screenshots of the sidebar page from a running Home Assistant.

    pip install playwright          # once; Windows uses the installed Edge
    python -m playwright install chromium   # once, only without Edge or Chrome

    HA_URL=http://homeassistant.local:8123 HA_TOKEN=<long-lived token> \
        python scripts/screenshots.py

The token is a long-lived access token of an admin (your profile -> Security),
from HA_TOKEN or else the first line of ha_token in the repository (git-ignored);
it is never written anywhere. Home Assistant has to run the version in this
repository's manifest (update it first). The pictures go to images/:

    overview.png       Devices
    device-page.png    a device's page (--device, else the first running purifier)
    groups.png         Purifier groups
    group-page.png     a group's page (--group, else the first group; none: skipped)
    group-editor.png   that group's editor
    panel-updates.png  Updates & config

Each picture is as tall as the page, at --width (default 1280) CSS pixels,
without Home Assistant's sidebar (--sidebar to keep it).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time

PANEL = "levoit-esphome"
TAG = "levoit-esphome-panel"
ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE_HEIGHT = 900
# bottom of the panel's content, in page pixels
MEASURE = """e => {
  const top = window.scrollY;
  const parts = [e, ...(e.shadowRoot ? e.shadowRoot.children : [])];
  const bottom = (c) => c.getBoundingClientRect().top + top + c.scrollHeight;
  return Math.ceil(Math.max(...parts.map(bottom)));
}"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--url", default=os.environ.get("HA_URL", "http://homeassistant.local:8123"))
    p.add_argument(
        "--device", help="device name as in its page's URL (default: the first running purifier)"
    )
    p.add_argument("--group", help="group id for its page and editor (default: the first group)")
    p.add_argument("--out", type=pathlib.Path, default=ROOT / "images")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument(
        "--scale", type=float, default=1, help="device pixel ratio, 2 for sharper pictures"
    )
    p.add_argument("--dark", action="store_true", help="Home Assistant's dark theme")
    p.add_argument("--sidebar", action="store_true", help="with Home Assistant's sidebar")
    p.add_argument(
        "--settle", type=float, default=3, help="seconds to wait for live data and history"
    )
    p.add_argument("--only", nargs="*", help="only these pictures, e.g. overview device-page")
    p.add_argument("--headed", action="store_true", help="show the browser")
    p.add_argument(
        "--token-file",
        type=pathlib.Path,
        default=ROOT / "ha_token",
        help="file with the token, when HA_TOKEN is not set (default: ha_token, git-ignored)",
    )
    return p.parse_args()


def login_script(url: str, token: str, dark: bool, hide_sidebar: bool) -> str:
    """localStorage as the frontend keeps it after a login, with the long-lived token."""
    tokens = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 315360000,
        "expires": int(time.time() * 1000) + 315360000 * 1000,
        "refresh_token": "",
        "hassUrl": url,
        "clientId": url + "/",
    }
    items = {
        "hassTokens": json.dumps(tokens),
        "selectedTheme": json.dumps({"theme": "default", "dark": dark}),
    }
    if hide_sidebar:
        items["dockedSidebar"] = json.dumps("always_hidden")
    sets = "".join(
        f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in items.items()
    )
    return f"try {{ {sets} }} catch (e) {{}}"


async def launch(pw, headed: bool):
    """The installed Edge or Chrome first, then Playwright's own Chromium."""
    last = None
    for channel in ("msedge", "chrome", None):
        try:
            return await pw.chromium.launch(channel=channel, headless=not headed)
        except Exception as err:
            last = err
    raise SystemExit(f"No browser found ({last}). Run: python -m playwright install chromium")


async def main() -> int:  # noqa: PLR0915 - one run, top to bottom
    args = parse_args()
    token = os.environ.get("HA_TOKEN")
    if not token and args.token_file.is_file():
        # the first line with something on it (a BOM from an editor is dropped)
        lines = args.token_file.read_text(encoding="utf-8-sig").splitlines()
        token = next((line.strip() for line in lines if line.strip()), "")
    if not token:
        print(
            f"Set HA_TOKEN, or put the token in {args.token_file}: a long-lived access token"
            " (profile -> Security).",
            file=sys.stderr,
        )
        return 2
    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415 - optional
    except ImportError:
        print("pip install playwright", file=sys.stderr)
        return 2

    url = args.url.rstrip("/")
    args.out.mkdir(parents=True, exist_ok=True)
    want = set(args.only or [])

    async with async_playwright() as pw:
        browser = await launch(pw, args.headed)
        context = await browser.new_context(
            viewport={"width": args.width, "height": BASE_HEIGHT},
            device_scale_factor=args.scale,
            color_scheme="dark" if args.dark else "light",
        )
        await context.add_init_script(login_script(url, token, args.dark, not args.sidebar))
        page = await context.new_page()
        panel = page.locator(TAG)

        async def open_(path: str) -> None:
            try:
                await page.goto(f"{url}/{PANEL}{path}")
            except Exception as err:
                raise SystemExit(f"Cannot open {url}: {str(err).splitlines()[0]}") from None
            try:
                await panel.wait_for(state="attached", timeout=30000)
            except Exception:
                if "/auth/" in page.url:
                    raise SystemExit("Not logged in: check HA_URL and HA_TOKEN.") from None
                raise SystemExit(f"The sidebar page did not open at {page.url}.") from None
            await page.wait_for_timeout(args.settle * 1000)

        async def shoot(name: str) -> None:
            if want and name not in want:
                return
            await page.mouse.move(0, 0)  # no hover on a card
            # measured at the base height: the page is at least 100vh tall
            await page.set_viewport_size({"width": args.width, "height": BASE_HEIGHT})
            await page.wait_for_timeout(300)
            height = max(BASE_HEIGHT, min(await panel.evaluate(MEASURE), 6000))
            await page.set_viewport_size({"width": args.width, "height": height})
            await page.wait_for_timeout(500)
            path = args.out / f"{name}.png"
            await page.screenshot(path=str(path))
            print(f"{path}  ({args.width}x{height})")

        async def ws(message: dict):
            return await page.evaluate(
                "m => document.querySelector('home-assistant')"
                ".hass.connection.sendMessagePromise(m)",
                message,
            )

        await open_("")
        manifest = json.loads(
            (ROOT / "custom_components" / "levoit_esphome" / "manifest.json").read_text("utf-8")
        )
        running = (await ws({"type": "manifest/get", "integration": "levoit_esphome"}))["version"]
        if running != manifest["version"]:
            raise SystemExit(
                f"Home Assistant runs {running}, the repository {manifest['version']}: "
                "update it first."
            )
        await shoot("overview")

        device = args.device
        if not device:
            # a running purifier shows the most; else any online one
            for selector in (".dcard.on", ".dcard:not(.offline)"):
                first = page.locator(f"{TAG} {selector}").first
                if await first.count():
                    path = await first.get_attribute("data-path") or ""
                    device = path.rsplit("/", 1)[-1] or None
                    break
        if device:
            await open_(f"/device/{device}")
            await shoot("device-page")
        else:
            print("device-page skipped: no online device (--device NAME)")

        await open_("/groups")
        await shoot("groups")

        group = args.group
        if not group:
            groups = (await ws({"type": "levoit_esphome/groups/list"})) or {}
            ids = (
                [g.get("id") for g in groups.get("groups", [])] if isinstance(groups, dict) else []
            )
            group = next((i for i in ids if i), None)
        if group:
            await open_(f"/groups/{group}")
            await shoot("group-page")
            await open_(f"/groups/{group}/edit")
            await shoot("group-editor")
        else:
            print("group-page and group-editor skipped: no group yet")

        await open_("/config")
        await shoot("panel-updates")
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
