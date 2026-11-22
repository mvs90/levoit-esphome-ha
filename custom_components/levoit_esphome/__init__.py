"""Levoit ESPHome: updates for devices running the levoit / philips components."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .coordinator import LevoitEsphomeCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR, Platform.UPDATE]

type LevoitEsphomeConfigEntry = ConfigEntry[LevoitEsphomeCoordinator]


@callback
def _async_drop_via_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the "connected via" link the first version set.

    Home Assistant keeps via_device_id on a device even when the entities no
    longer set it; the purifier's ESPHome device is listed under "Linked
    devices" through the shared MAC instead.
    """
    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if device.via_device_id is not None:
            dev_reg.async_update_device(device.id, via_device_id=None)


async def async_setup_entry(hass: HomeAssistant, entry: LevoitEsphomeConfigEntry) -> bool:
    """Set up from a config entry."""
    _async_drop_via_device(hass, entry)
    coordinator = LevoitEsphomeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LevoitEsphomeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
