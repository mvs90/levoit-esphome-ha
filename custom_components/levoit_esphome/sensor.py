"""Sensors: filter life, and versions, model, channel and config of a device.

Also per purifier group: its level and air quality, and its combined value of
each sensor type it has (PM1, PM2.5, PM10, AQI index) and its purifiers' total
CADR, so Home Assistant keeps their history. Those are added when the group
gets a sensor of that type and removed when it has none any more.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from .const import CHANNEL_LOCAL, CHANNEL_MAIN, CHANNEL_PINNED, CHANNEL_STABLE, DOMAIN
from .coordinator import LevoitData, LevoitDevice
from .entity import LevoitEsphomeEntity, async_add_per_device
from .group_entity import LevoitGroupEntity, async_add_per_group
from .groups import CADR, SIGNAL_GROUPS, signal_group
from .groups_logic import AQI, PM1, PM10, PM25
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
    """Set up the diagnostic sensors per device, and level and air quality per group."""
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
            lambda manager, group_id: [
                GroupLevelSensor(manager, group_id),
                GroupAirQualitySensor(manager, group_id),
            ],
        )
    )
    entry.async_on_unload(
        _async_add_group_values(hass, entry.runtime_data.groups, async_add_entities)
    )


GROUP_VALUES: dict[str, SensorEntityDescription] = {
    PM1: SensorEntityDescription(
        key=PM1,
        translation_key="group_pm1",
        device_class=SensorDeviceClass.PM1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    PM25: SensorEntityDescription(
        key=PM25,
        translation_key="group_pm25",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    PM10: SensorEntityDescription(
        key=PM10,
        translation_key="group_pm10",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    # the Levoit level 1-4, not the 0-500 AQI device class
    AQI: SensorEntityDescription(
        key=AQI,
        translation_key="group_aqi",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    CADR: SensorEntityDescription(
        key=CADR,
        translation_key="group_cadr",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
}


@callback
def _async_add_group_values(
    hass: HomeAssistant,
    manager: GroupManager,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> Callable[[], None]:
    """Per group, one sensor per value it has; added and removed as that changes."""
    added: dict[str, set[str]] = {}  # group id -> value keys with an entity
    unsubs: dict[str, CALLBACK_TYPE] = {}

    @callback
    def _sync(group_id: str) -> None:
        wanted = set(manager.value_types(group_id))
        have = added.setdefault(group_id, set())
        if new := [k for k in GROUP_VALUES if k in wanted and k not in have]:
            have.update(new)
            async_add_entities(GroupValueSensor(manager, group_id, k) for k in new)
        if gone := have - wanted:
            have.difference_update(gone)
            ent_reg = er.async_get(hass)
            for key in gone:
                if entity_id := ent_reg.async_get_entity_id(
                    "sensor", DOMAIN, f"group_{group_id}_{key}"
                ):
                    ent_reg.async_remove(entity_id)

    @callback
    def _groups_changed() -> None:
        for group_id in manager.groups:
            if group_id not in unsubs:
                unsubs[group_id] = async_dispatcher_connect(
                    hass, signal_group(group_id), partial(_sync, group_id)
                )
                _sync(group_id)
        # a deleted group's entities go with its device
        for group_id in [g for g in unsubs if g not in manager.groups]:
            unsubs.pop(group_id)()
            added.pop(group_id, None)

    _groups_changed()
    unsub_added = async_dispatcher_connect(hass, SIGNAL_GROUPS, _groups_changed)
    unsub_list = manager.async_add_listener(_groups_changed)

    @callback
    def _unsub() -> None:
        unsub_added()
        unsub_list()
        for unsub in unsubs.values():
            unsub()
        unsubs.clear()

    return _unsub


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
    """A purifier group's level: 1-4, or 0 while it lets go (no sensor value, paused)."""

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


class GroupAirQualitySensor(LevoitGroupEntity, SensorEntity):
    """A purifier group's air quality, 1-4: its worst sensor type on the group's thresholds.

    Unlike the level, no hold time and no rising-fast jump, and it reads the
    same in Manual or with the group off.
    """

    _attr_translation_key = "group_air_quality"
    _attr_icon = "mdi:air-filter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, manager: GroupManager, group_id: str) -> None:
        """Initialize."""
        super().__init__(manager, group_id, "air_quality")

    @property
    def native_value(self) -> int | None:
        """1-4; unknown while no sensor has a number."""
        return self.group_state["air_quality"] if self.group is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The worst sensor and each sensor's level."""
        if self.group is None:
            return None
        state = self.group_state
        return {
            "worst_sensor": state["air_quality_sensor"],
            "sensor_levels": state["air_quality_levels"],
        }


class GroupValueSensor(LevoitGroupEntity, SensorEntity):
    """A purifier group's combined value of one sensor type, or its total CADR.

    The type's sensors combined as the group says (highest, average, median or
    lowest): the value its level comes from. CADR is the sum of its purifiers'.
    """

    def __init__(self, manager: GroupManager, group_id: str, key: str) -> None:
        """Initialize."""
        super().__init__(manager, group_id, key)
        self.entity_description = GROUP_VALUES[key]

    @property
    def _value(self) -> dict[str, Any] | None:
        if self.group is None:
            return None
        state = self.group_state
        if self.entity_description.key == CADR:
            return state["cadr"]
        return state["values"].get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Available while one of its sensors has a number."""
        value = self._value
        return super().available and value is not None and value["value"] is not None

    @property
    def native_value(self) -> float | None:
        """The combined value."""
        value = self._value
        return round(value["value"], 2) if value and value["value"] is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """How it is combined, from which sensors, and the level it gives."""
        value = self._value
        if value is None:
            return None
        if self.entity_description.key == CADR:
            return {"sensors": value["sensors"]}
        return {"combine": value["how"], "sensors": value["sensors"], "level": value["level"]}
