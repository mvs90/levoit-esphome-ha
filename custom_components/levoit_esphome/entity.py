"""Base entity: on our own device per purifier, linked to its ESPHome device."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LevoitDevice, LevoitEsphomeCoordinator
from .device_builder import builder_page_url


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
        # "Visit" on the device page opens the Device Builder add-on
        if page := builder_page_url(coordinator.device_builder):
            self._attr_device_info["configuration_url"] = f"homeassistant:/{page}"

    @property
    def device(self) -> LevoitDevice | None:
        """Current data of this device."""
        return self.coordinator.data.devices.get(self._device_name)

    @property
    def available(self) -> bool:
        """Available while the device is found (not only remembered, offline)."""
        device = self.device
        return super().available and device is not None and device.detected


def subentry_for(entry: ConfigEntry, name: str) -> str | None:
    """The "Add device" sub-entry made for a device (its unique ID is the device name)."""
    return next(
        (
            sub.subentry_id
            for sub in entry.subentries.values()
            if sub.subentry_type == "device" and sub.unique_id == name
        ),
        None,
    )


def async_add_per_device(
    coordinator: LevoitEsphomeCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[LevoitEsphomeCoordinator, str], Iterable[Entity]],
) -> Callable[[], None]:
    """Add entities for every device, now and when new devices show up."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        # each device with the "Add device" sub-entry of its config, if any
        for name in coordinator.data.devices:
            if name in known:
                continue
            entities = list(factory(coordinator, name))
            if not entities:
                continue
            known.add(name)
            async_add_entities(
                entities,
                config_subentry_id=subentry_for(coordinator.config_entry, name),
            )

    _add_new()
    return coordinator.async_add_listener(_add_new)
