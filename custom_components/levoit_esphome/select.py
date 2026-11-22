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
    """Which channel to compare a device without a config against.

    With a Device Builder config the component's `ref:` there decides, and this
    select is unavailable. Without one there is nothing to read the channel
    from, so the user picks it; the update entity then says whether a newer
    version is out (installing still needs a config).
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
            self.coordinator.async_choose_channel(self._device_name, last.state)

    @property
    def available(self) -> bool:
        """Only for a device without a Device Builder config."""
        device = self.device
        return super().available and device is not None and not device.configuration

    @property
    def current_option(self) -> str | None:
        """The chosen channel."""
        device = self.device
        if device is None or not device.channel_chosen:
            return None
        return device.channel

    async def async_select_option(self, option: str) -> None:
        """Choose the channel."""
        self.coordinator.async_choose_channel(self._device_name, option)
