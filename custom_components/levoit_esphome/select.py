"""Update channel of a device that has no Device Builder config."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CHANNEL_MAIN, CHANNEL_STABLE
from .entity import LevoitEsphomeEntity, async_add_per_device

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import LevoitEsphomeConfigEntry
    from .coordinator import LevoitEsphomeCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LevoitEsphomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the channel select per device."""
    entry.async_on_unload(
        async_add_per_device(
            entry.runtime_data,
            async_add_entities,
            lambda coordinator, name: [LevoitChannelSelect(coordinator, name)],
        )
    )


class LevoitChannelSelect(LevoitEsphomeEntity, SelectEntity, RestoreEntity):
    """The channel a device follows: stable (releases) or main (every merge).

    * No Device Builder config: what the device is compared with (installing
      still needs a config); restored after a restart.
    * Template config: rewrites the component's `ref:` in the config; the next
      install builds from the new channel.
    * Custom config: unavailable, its own `ref:` decides (edit it there).
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "update_channel"

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, name, "update_channel")
        self._attr_options = [CHANNEL_STABLE, CHANNEL_MAIN]

    async def async_added_to_hass(self) -> None:
        """Restore the last choice."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in self.options:
            # only a choice without a config; a config's ref: is read from it
            self.coordinator.async_choose_channel(self._device_name, last.state)

    @property
    def available(self) -> bool:
        """Without a config, or with a template config."""
        device = self.device
        return super().available and device is not None and self.coordinator.can_set_channel(device)

    @property
    def current_option(self) -> str | None:
        """The device's channel (None for a pinned ref)."""
        device = self.device
        if device is None or device.channel not in self.options:
            return None
        return device.channel

    async def async_select_option(self, option: str) -> None:
        """Switch the channel (rewrites a template config's ref:)."""
        device = self.device
        if device is None:
            return
        await self.coordinator.async_set_channel(device, option)
