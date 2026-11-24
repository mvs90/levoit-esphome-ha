"""Sensors: filter life, and versions, model, channel and config of a device.

Also the level of each purifier group.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CHANNEL_LOCAL, CHANNEL_MAIN, CHANNEL_PINNED, CHANNEL_STABLE
from .coordinator import LevoitData, LevoitDevice
from .entity import LevoitEsphomeEntity, async_add_per_device
from .group_entity import LevoitGroupEntity, async_add_per_group
from .templates import VARIANT_CUSTOM, VARIANTS

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import LevoitEsphomeConfigEntry
    from .coordinator import LevoitEsphomeCoordinator
    from .groups import GroupManager

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LevoitSensorDescription(SensorEntityDescription):
    """A diagnostic value of a device."""

    value_fn: Callable[[LevoitDevice, LevoitData], str | None]


def _latest(device: LevoitDevice, data: LevoitData) -> str | None:
    """Newest version on the device's channel (None: no channel or no GitHub yet)."""
    head = data.heads.get(device.channel) if device.channel else None
    return head.text if head else None


SENSORS: tuple[LevoitSensorDescription, ...] = (
    LevoitSensorDescription(
        key="installed_version",
        translation_key="installed_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: device.reported.text if device.reported else None,
    ),
    LevoitSensorDescription(
        key="latest_version",
        translation_key="latest_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_latest,
    ),
    LevoitSensorDescription(
        key="model",
        translation_key="model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: device.model,
    ),
    LevoitSensorDescription(
        key="channel",
        translation_key="channel",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=[CHANNEL_STABLE, CHANNEL_MAIN, CHANNEL_PINNED, CHANNEL_LOCAL],
        value_fn=lambda device, _: device.channel,
    ),
    LevoitSensorDescription(
        key="config_kind",
        translation_key="config_kind",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=[*VARIANTS, VARIANT_CUSTOM],
        value_fn=lambda device, _: (
            device.config_kind if device.config_kind in (*VARIANTS, VARIANT_CUSTOM) else None
        ),
    ),
    LevoitSensorDescription(
        key="configuration",
        translation_key="configuration",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: device.configuration,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LevoitEsphomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the diagnostic sensors per device, and the level per group."""
    entry.async_on_unload(
        async_add_per_device(
            entry.runtime_data,
            async_add_entities,
            lambda coordinator, name: [
                LevoitFilterSensor(coordinator, name),
                *(LevoitDiagnosticSensor(coordinator, name, d) for d in SENSORS),
            ],
        )
    )
    entry.async_on_unload(
        async_add_per_group(
            entry.runtime_data.groups,
            async_add_entities,
            lambda manager, group_id: [GroupLevelSensor(manager, group_id)],
        )
    )


class LevoitDiagnosticSensor(LevoitEsphomeEntity, SensorEntity):
    """Model, channel or config file of a device."""

    entity_description: LevoitSensorDescription

    def __init__(
        self,
        coordinator: LevoitEsphomeCoordinator,
        name: str,
        description: LevoitSensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, name, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        """The value, None while unknown."""
        device = self.device
        if device is None:
            return None
        return self.entity_description.value_fn(device, self.coordinator.data)


class LevoitFilterSensor(LevoitEsphomeEntity, SensorEntity):
    """The purifier's filter life, from its own ESPHome filter sensor.

    Follows that sensor's state directly (no Device Builder poll); which
    sensor it is comes from the coordinator (see coordinator._filter_score).
    """

    _attr_translation_key = "filter_life"
    _attr_icon = "mdi:air-filter"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, name, "filter_life")
        self._source: str | None = None
        self._unsub_source: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        """Start following the source sensor."""
        await super().async_added_to_hass()
        self._follow_source()
        self.async_on_remove(self._stop_following)

    @callback
    def _handle_coordinator_update(self) -> None:
        """The source may have changed (renamed, re-added)."""
        self._follow_source()
        super()._handle_coordinator_update()

    @callback
    def _follow_source(self) -> None:
        device = self.device
        source = device.filter_entity_id if device is not None else None
        if source == self._source:
            return
        self._stop_following()
        self._source = source
        if source is not None:
            self._unsub_source = async_track_state_change_event(
                self.hass, [source], self._source_changed
            )

    @callback
    def _stop_following(self) -> None:
        if self._unsub_source is not None:
            self._unsub_source()
            self._unsub_source = None

    @callback
    def _source_changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Available while the device's filter sensor has a number."""
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        """The filter sensor's value."""
        device = self.device
        if device is None or device.filter_entity_id is None:
            return None
        state = self.hass.states.get(device.filter_entity_id)
        if state is None:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None


class GroupLevelSensor(LevoitGroupEntity, SensorEntity):
    """A purifier group's level: 0 (air is clean) to its max speed."""

    _attr_translation_key = "group_level"
    _attr_icon = "mdi:air-purifier"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, manager: GroupManager, group_id: str) -> None:
        """Initialize."""
        super().__init__(manager, group_id, "level")

    @property
    def native_value(self) -> int | None:
        """The level."""
        return self.group_state["level"] if self.group is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Status, why, the worst sensor and the members in control."""
        if self.group is None:
            return None
        state = self.group_state
        return {
            "status": state["status"],
            "reason": state["reason"],
            "worst_sensor": state["worst"],
            "members_in_control": [m["entity_id"] for m in state["members"] if m["in_control"]],
        }
