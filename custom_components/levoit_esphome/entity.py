"""Base entity: on our own device per purifier, linked to its ESPHome device."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LevoitDevice, LevoitEsphomeCoordinator


class LevoitEsphomeEntity(CoordinatorEntity[LevoitEsphomeCoordinator]):
    """An entity of one Levoit / Philips ESPHome device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_name = name
        device = coordinator.data.devices[name]
        self._attr_unique_id = f"{device.mac}-{key}"
        # Since Home Assistant 2026.8 identifiers and connections are unique per
        # config entry only: a matching MAC no longer merges into the ESPHome
        # integration's device. So this is our own device, named like the
        # purifier. The shared MAC connection makes Home Assistant list the
        # ESPHome device under "Linked devices"; no via_device ("connected
        # via" would mean routed through it).
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.mac)},
            connections={(CONNECTION_NETWORK_MAC, device.mac)},
            name=device.title,
            manufacturer="tuct/levoit",
            model="ESPHome component",
        )

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
