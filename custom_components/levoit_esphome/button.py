"""Compile button: build in the Device Builder without uploading."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from typing import TYPE_CHECKING, Any

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
            lambda coordinator, name: [LevoitCompileButton(coordinator, name)],
        )
    )


class LevoitCompileButton(LevoitEsphomeEntity, ButtonEntity):
    """Compile the device's config, to check a build before uploading."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "compile"

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, name, "compile")

    @property
    def available(self) -> bool:
        """Only with a Device Builder config."""
        device = self.device
        return super().available and device is not None and bool(device.configuration)

    async def async_press(self) -> None:
        """Compile."""
        device = self.device
        builder = self.coordinator.device_builder
        if device is None or not device.configuration:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_configuration")
        if builder is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_device_builder")
        lock: AbstractAsyncContextManager[Any] = (
            nullcontext()
            if getattr(builder, "supports_build_queue", False)
            else self.coordinator.build_lock
        )
        async with lock:
            compiled = await builder.api.compile(device.configuration)
        if not compiled:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="compile_failed",
                translation_placeholders={"configuration": device.configuration},
            )
