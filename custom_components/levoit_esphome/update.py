"""Update entity: the device's component version against its channel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CHANNEL_MAIN, CHANNEL_STABLE, DOMAIN, GITHUB_REPO
from .entity import LevoitEsphomeEntity, async_add_per_device
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

    @property
    def in_progress(self) -> bool:
        """While any build of the device runs (install, compile, compile and upload)."""
        return self.coordinator.is_building(self._device_name)

    @property
    def update_percentage(self) -> int | None:
        """Rough progress by step: config 5 %, compile 10 %, upload 85 %."""
        return self.coordinator.build_progress(self._device_name)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Compile in the Device Builder, then upload over the air."""
        device = self.device
        if device is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_configuration")
        await self.coordinator.async_build(device, upload=True)
