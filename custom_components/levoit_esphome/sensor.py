"""Diagnostic sensors: versions, model, channel and Device Builder config of a device."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from .const import CHANNEL_LOCAL, CHANNEL_MAIN, CHANNEL_PINNED, CHANNEL_STABLE
from .coordinator import LevoitData, LevoitDevice
from .entity import LevoitEsphomeEntity, async_add_per_device

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import LevoitEsphomeConfigEntry
    from .coordinator import LevoitEsphomeCoordinator

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
    """Set up the diagnostic sensors per device."""
    entry.async_on_unload(
        async_add_per_device(
            entry.runtime_data,
            async_add_entities,
            lambda coordinator, name: [
                LevoitDiagnosticSensor(coordinator, name, description) for description in SENSORS
            ],
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
