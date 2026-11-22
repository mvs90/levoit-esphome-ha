"""Base entity: attached to the device's existing ESPHome device."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LevoitDevice, LevoitEsphomeCoordinator


class LevoitEsphomeEntity(CoordinatorEntity[LevoitEsphomeCoordinator]):
    """An entity of one Levoit / Philips ESPHome device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_name = name
        mac = coordinator.data.devices[name].mac
        self._attr_unique_id = f"{mac}-{key}"
        # Same MAC connection as the ESPHome device: the registry merges them,
        # so these entities show up on the purifier's own device page.
        self._attr_device_info = DeviceInfo(connections={(CONNECTION_NETWORK_MAC, mac)})

    @property
    def device(self) -> LevoitDevice | None:
        """Current data of this device."""
        return self.coordinator.data.devices.get(self._device_name)

    @property
    def available(self) -> bool:
        """Available while the device is known."""
        return super().available and self.device is not None


def async_add_per_device(
    coordinator: LevoitEsphomeCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[LevoitEsphomeCoordinator, str], Iterable[Entity]],
) -> Callable[[], None]:
    """Add entities for every device, now and when new devices show up."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [name for name in coordinator.data.devices if name not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(entity for name in new for entity in factory(coordinator, name))

    _add_new()
    return coordinator.async_add_listener(_add_new)
