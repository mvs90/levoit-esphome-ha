"""Base entity of a purifier group: one device per group, updated by its runner."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .groups import SIGNAL_GROUPS, GroupManager, group_identifier, signal_group
from .groups_logic import GroupConfig


class LevoitGroupEntity(Entity):
    """An entity of one purifier group."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: GroupManager, group_id: str, key: str) -> None:
        """Initialize."""
        self._manager = manager
        self._group_id = group_id
        self._attr_unique_id = f"group_{group_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={group_identifier(group_id)},
            name=manager.groups[group_id].name,
            manufacturer="Levoit ESPHome",
            model="Purifier group",
            entry_type=DeviceEntryType.SERVICE,
        )

    # not `group`: Home Assistant 2026.10 reserves Entity.group for its own
    # entity groups and warns about anything else there (an error from 2027.2)
    @property
    def purifier_group(self) -> GroupConfig | None:
        """The group's config (None once deleted)."""
        return self._manager.groups.get(self._group_id)

    @property
    def group_state(self) -> dict[str, Any]:
        """The group's status, level and members."""
        return self._manager.state(self._group_id)

    @property
    def available(self) -> bool:
        """Available while the group exists."""
        return self.purifier_group is not None

    async def async_added_to_hass(self) -> None:
        """Follow the group."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_group(self._group_id), self.async_write_ha_state
            )
        )


def async_add_per_group(
    manager: GroupManager,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[GroupManager, str], Iterable[Entity]],
) -> Callable[[], None]:
    """Add entities for every group, now and when one is created."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [group_id for group_id in manager.groups if group_id not in known]
        known.update(new)
        for group_id in new:
            async_add_entities(factory(manager, group_id))

    _add_new()
    return async_dispatcher_connect(manager.hass, SIGNAL_GROUPS, _add_new)
