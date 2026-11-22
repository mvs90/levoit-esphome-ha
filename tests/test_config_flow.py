"""Config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from custom_components.levoit_esphome.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def test_abort_without_device_builder(hass: HomeAssistant) -> None:
    """No Device Builder add-on: nothing to set up."""
    hass.config.components.add("esphome")
    with patch(
        "custom_components.levoit_esphome.config_flow.async_get_device_builder",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_device_builder"


async def test_create_entry(
    hass: HomeAssistant, patch_sources: AsyncMock, esphome_devices: dict
) -> None:
    """With a Device Builder: confirm and create the one entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Levoit ESPHome"

    # single_config_entry: a second one is refused
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
