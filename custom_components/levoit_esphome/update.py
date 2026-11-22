"""Update entity: the device's component version against its channel."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CHANNEL_MAIN, CHANNEL_STABLE, DOMAIN, GITHUB_REPO
from .device_builder import DeviceBuilderCommandError
from .entity import LevoitEsphomeEntity, async_add_per_device
from .templates import TemplateError
from .versions import ChannelHead, is_behind

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
    """Set up an update entity per device."""
    entry.async_on_unload(
        async_add_per_device(
            entry.runtime_data,
            async_add_entities,
            lambda coordinator, name: [LevoitFirmwareUpdate(coordinator, name)],
        )
    )


class LevoitFirmwareUpdate(LevoitEsphomeEntity, UpdateEntity):
    """Rebuild the device from its config when its channel moved on."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_translation_key = "firmware"

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, name, "firmware")
        self._attr_in_progress = False

    @property
    def _head(self) -> ChannelHead | None:
        device = self.device
        if device is None or device.channel is None:
            return None
        return self.coordinator.data.heads.get(device.channel)

    @property
    def supported_features(self) -> UpdateEntityFeature:
        """Install only for a device with a config on a known channel."""
        features = UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
        device = self.device
        if device is not None and device.configuration and self._head is not None:
            features |= UpdateEntityFeature.INSTALL
        return features

    @property
    def title(self) -> str:
        """Which component."""
        device = self.device
        if device is not None and device.components == {"philips"}:
            return "Philips component"
        return "Levoit component"

    @property
    def installed_version(self) -> str | None:
        """What the device reports through its `esp_version` sensor."""
        device = self.device
        if device is None or device.reported is None:
            return None
        return device.reported.text

    @property
    def latest_version(self) -> str | None:
        """Head of the device's channel.

        None (state unknown) without a channel (no Device Builder config, a
        pinned ref) or while GitHub has not answered: "up to date" would be
        a guess.
        """
        head = self._head
        return None if head is None else head.text

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """main compares commits, stable compares releases (see versions.is_behind)."""
        device = self.device
        head = self._head
        if device is None or device.reported is None or head is None or device.channel is None:
            return False
        return is_behind(device.reported, head, device.channel)

    @property
    def release_url(self) -> str | None:
        """Release page (stable) or the commits since this build (main)."""
        device = self.device
        head = self._head
        if device is None or head is None:
            return None
        if (
            device.channel == CHANNEL_MAIN
            and device.reported is not None
            and device.reported.commit
        ):
            return (
                f"https://github.com/{GITHUB_REPO}/compare/{device.reported.commit}...{head.commit}"
            )
        return head.url

    async def async_release_notes(self) -> str | None:
        """Release notes (stable) or a pointer to the commits (main)."""
        device = self.device
        head = self._head
        if device is None or head is None:
            return None
        if device.channel == CHANNEL_STABLE:
            return head.notes
        return f"Builds from `main`, now at {head.text}. Changes: {self.release_url}"

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Compile in the Device Builder, then upload over the air."""
        device = self.device
        builder = self.coordinator.device_builder
        if device is None or not device.configuration:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_configuration")
        if builder is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_device_builder")
        configuration = device.configuration
        lock: AbstractAsyncContextManager[Any] = (
            nullcontext()
            if getattr(builder, "supports_build_queue", False)
            else self.coordinator.build_lock
        )

        self._attr_in_progress = True
        self.async_write_ha_state()
        try:
            if device.template:
                # Original / C3 configs follow the newest builder file; a custom
                # config only gets the new component through its ref.
                try:
                    await self.coordinator.async_refresh_from_template(builder, configuration)
                except (DeviceBuilderCommandError, TemplateError, ClientError, TimeoutError) as err:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="template_refresh_failed",
                        translation_placeholders={
                            "configuration": configuration,
                            "error": str(err),
                        },
                    ) from err
            async with lock:
                compiled = await builder.api.compile(configuration)
            if not compiled:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="compile_failed",
                    translation_placeholders={"configuration": configuration},
                )
            if not await builder.api.upload(configuration, "OTA"):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="upload_failed",
                    translation_placeholders={"configuration": configuration},
                )
        finally:
            self._attr_in_progress = False
            self.coordinator.async_forget_config(configuration)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
