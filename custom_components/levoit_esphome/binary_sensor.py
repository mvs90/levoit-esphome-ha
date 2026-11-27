"""Binary sensors: whether a purifier group is running its members."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant

from .group_entity import LevoitGroupEntity, async_add_per_group

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import LevoitEsphomeConfigEntry
    from .groups import GroupManager

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LevoitEsphomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the active sensor per purifier group."""
    entry.async_on_unload(
        async_add_per_group(
            entry.runtime_data.groups,
            async_add_entities,
            lambda manager, group_id: [GroupActiveSensor(manager, group_id)],
        )
    )


class GroupActiveSensor(LevoitGroupEntity, BinarySensorEntity):
    """On while the group runs at a level above 0."""

    _attr_translation_key = "group_active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, manager: GroupManager, group_id: str) -> None:
        """Initialize."""
        super().__init__(manager, group_id, "active")

    @property
    def is_on(self) -> bool:
        """Level above 0."""
        return self.purifier_group is not None and self.group_state["level"] > 0
