"""Access to the ESPHome Device Builder.

The integration does not talk to the Device Builder itself. It uses the
connection Home Assistant's ESPHome integration keeps to the Device Builder
add-on (found through Supervisor discovery). That is internal to the esphome
integration, so all of it goes through this module: when Home Assistant
changes it, only this file has to follow.

The Device Builder endpoints behind it (/devices, /json-config, /compile,
/upload) are kept by the Device Builder for Home Assistant only; going
through Home Assistant's object means we move along when Home Assistant
moves to their newer API.

Writing files (configs, secrets.yaml) is not in that legacy API. It goes
through the Device Builder's own /ws API at the same address: Home
Assistant's address is the add-on's trusted (Supervisor) site, where a
connection is authenticated from the start. Only secret *names* are ever
read from secrets.yaml, never values.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import itertools
from typing import Any, Protocol

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_WS_TIMEOUT = 60
_message_ids = itertools.count(1)


class DeviceBuilderApi(Protocol):
    """The part of esphome_dashboard_api.ESPHomeDashboardAPI we use."""

    async def get_devices(self) -> dict[str, Any]:
        """Configured and importable devices."""

    async def get_config(self, configuration: str) -> dict[str, Any] | None:
        """A config fully resolved (secrets included: never log or store it)."""

    async def compile(
        self, configuration: str, line_received_cb: Callable[[str], None] | None = None
    ) -> bool:
        """Compile a config."""

    async def upload(
        self,
        configuration: str,
        port: str,
        line_received_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Upload the last build of a config."""


class DeviceBuilder(Protocol):
    """The part of the esphome integration's dashboard coordinator we use."""

    api: DeviceBuilderApi
    supports_build_queue: bool
    url: str
    addon_slug: str


def builder_page_url(builder: DeviceBuilder | None) -> str | None:
    """The Device Builder add-on's page in Home Assistant (a relative URL).

    /app/<slug> is the frontend's add-on panel; it works whether or not the
    add-on is shown in the sidebar (/<slug>). /hassio/ingress/<slug> is gone.
    """
    slug = getattr(builder, "addon_slug", None) if builder is not None else None
    return f"/app/{slug}" if slug else None


@callback
def async_get_device_builder(hass: HomeAssistant) -> DeviceBuilder | None:
    """Home Assistant's connection to the Device Builder add-on, if any."""
    # Internal API of the esphome integration (a dependency in manifest.json).
    from homeassistant.components.esphome.dashboard import (  # noqa: PLC0415
        async_get_dashboard,
    )

    return async_get_dashboard(hass)


class DeviceBuilderCommandError(Exception):
    """A /ws command failed; `code` is the Device Builder's error code."""

    def __init__(self, code: str, details: str = "") -> None:
        """Initialize."""
        super().__init__(f"{code}: {details}" if details else code)
        self.code = code
        self.details = details


async def _ws_command(
    hass: HomeAssistant, builder: DeviceBuilder, command: str, **args: Any
) -> Any:
    """Run one /ws command and return its result.

    One connection per command: these are rare, user-started actions.
    """
    message_id = str(next(_message_ids))
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(_WS_TIMEOUT):
            async with session.ws_connect(builder.url.rstrip("/") + "/ws") as ws:
                await ws.send_json({"command": command, "message_id": message_id, "args": args})
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    data = msg.json()
                    if data.get("message_id") != message_id or "event" in data:
                        continue  # the server info on connect, stream events
                    if "error_code" in data:
                        raise DeviceBuilderCommandError(
                            str(data["error_code"]), str(data.get("details", ""))
                        )
                    return data.get("result")
    except (aiohttp.ClientError, TimeoutError) as err:
        raise DeviceBuilderCommandError("unavailable", str(err)) from err
    raise DeviceBuilderCommandError("unavailable", "connection closed")


async def async_read_config(hass: HomeAssistant, builder: DeviceBuilder, configuration: str) -> str:
    """A config's YAML as written (not resolved)."""
    return str(await _ws_command(hass, builder, "devices/get_config", configuration=configuration))


async def async_write_config(
    hass: HomeAssistant, builder: DeviceBuilder, configuration: str, content: str, expected: str
) -> None:
    """Replace a config, only if it still holds `expected` (else precondition_failed)."""
    await _ws_command(
        hass,
        builder,
        "devices/update_config",
        configuration=configuration,
        content=content,
        expected=expected,
    )


async def async_create_config(
    hass: HomeAssistant, builder: DeviceBuilder, name: str, content: str
) -> str:
    """Create a config; returns its file name. Refuses an existing one (already_exists)."""
    result = await _ws_command(hass, builder, "devices/create", name=name, file_content=content)
    return str(result["configuration"])


async def async_secret_names(hass: HomeAssistant, builder: DeviceBuilder) -> set[str]:
    """The keys in secrets.yaml (names only, never values)."""
    return set(await _ws_command(hass, builder, "config/get_secrets") or [])


async def async_add_secret(
    hass: HomeAssistant, builder: DeviceBuilder, key: str, value: str
) -> bool:
    """Add a key to secrets.yaml unless it exists; True if it was added."""
    result = await _ws_command(
        hass, builder, "config/set_secret", key=key, value=value, overwrite=False
    )
    return bool(result.get("created")) if isinstance(result, dict) else False
