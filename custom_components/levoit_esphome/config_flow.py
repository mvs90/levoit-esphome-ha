"""Config flow: one entry, needs the ESPHome Device Builder add-on."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN
from .device_builder import async_get_device_builder


class LevoitEsphomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Levoit ESPHome."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm; abort without a Device Builder."""
        if async_get_device_builder(self.hass) is None:
            return self.async_abort(reason="no_device_builder")
        if user_input is not None:
            return self.async_create_entry(title="Levoit ESPHome", data={})
        return self.async_show_form(step_id="user")
