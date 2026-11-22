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
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from homeassistant.core import HomeAssistant, callback


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


@callback
def async_get_device_builder(hass: HomeAssistant) -> DeviceBuilder | None:
    """Home Assistant's connection to the Device Builder add-on, if any."""
    # Internal API of the esphome integration (a dependency in manifest.json).
    from homeassistant.components.esphome.dashboard import (  # noqa: PLC0415
        async_get_dashboard,
    )

    return async_get_dashboard(hass)
