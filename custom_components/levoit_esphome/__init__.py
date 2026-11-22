"""Levoit ESPHome: updates for devices running the levoit / philips components."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN
from .coordinator import LevoitEsphomeCoordinator
from .entity import subentry_for

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


@callback
def _async_move_to_subentries(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: LevoitEsphomeCoordinator
) -> None:
    """Put each device under the "Add device" sub-entry of its config.

    A device belongs to one sub-entry (Home Assistant 2026.8+). Adding its
    entities with another sub-entry would make a second device, so a device
    that exists already is moved, with its entities.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for name, device in coordinator.data.devices.items():
        target = subentry_for(entry, name)
        entry_device = dev_reg.async_get_device_by_identifier((DOMAIN, device.mac), entry.entry_id)
        if entry_device is None or entry_device.config_subentry_id == target:
            continue
        dev_reg.async_update_device(entry_device.id, new_config_subentry_id=target)
        for entity in er.async_entries_for_device(
            ent_reg, entry_device.id, include_disabled_entities=True
        ):
            if entity.config_entry_id == entry.entry_id and entity.config_subentry_id != target:
                ent_reg.async_update_entity(entity.entity_id, config_subentry_id=target)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A sub-entry was added or removed: set up again, so devices move under it."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: LevoitEsphomeConfigEntry) -> bool:
    """Set up from a config entry."""
    _async_drop_via_device(hass, entry)
    coordinator = LevoitEsphomeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _async_move_to_subentries(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LevoitEsphomeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
