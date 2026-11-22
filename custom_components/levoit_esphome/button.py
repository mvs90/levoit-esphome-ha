"""Compile button: build in the Device Builder without uploading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
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
    """Set up a compile button per device."""
    entry.async_on_unload(
        async_add_per_device(
            entry.runtime_data,
            async_add_entities,
            lambda coordinator, name: [
                LevoitCompileButton(coordinator, name),
                LevoitInstallButton(coordinator, name),
            ],
        )
    )


class LevoitCompileButton(LevoitEsphomeEntity, ButtonEntity):
    """Compile the device's config, to check a build before uploading."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "compile"
    _upload = False

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, name, self._attr_translation_key)

    @property
    def available(self) -> bool:
        """Only with a Device Builder config, and not while a build runs."""
        device = self.device
        return (
            super().available
            and device is not None
            and bool(device.configuration)
            and not self.coordinator.is_building(self._device_name)
        )

    async def async_press(self) -> None:
        """Build (and install)."""
        device = self.device
        if device is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_configuration")
        await self.coordinator.async_build(device, upload=self._upload)


class LevoitInstallButton(LevoitCompileButton):
    """Compile and upload over the air, also when the device is up to date."""

    _attr_translation_key = "install"
    _upload = True
