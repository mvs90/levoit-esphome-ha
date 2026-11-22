"""Coordinator: which devices are ours, what they run, what is available."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    COMPONENTS,
    CONFIG_INTERVAL,
    DOMAIN,
    GITHUB_INTERVAL,
    SCAN_INTERVAL,
)
from .device_builder import DeviceBuilder, async_get_device_builder
from .github import async_fetch_heads
from .versions import (
    ChannelHead,
    Reported,
    component_model,
    component_source,
    parse_reported,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

ESPHOME_DOMAIN = "esphome"


@dataclass(frozen=True)
class ConfigFacts:
    """What we keep from a resolved config: never the config itself (secrets)."""

    model: str | None
    channel: str | None
    ref: str | None
    read_at: datetime
    deployed_version: str | None


@dataclass
class LevoitDevice:
    """One ESPHome device that runs the levoit or philips component."""

    name: str
    mac: str
    title: str
    components: frozenset[str]
    reported: Reported | None
    version_entity_id: str | None
    configuration: str | None = None
    esphome_deployed: str | None = None
    esphome_current: str | None = None
    model: str | None = None
    channel: str | None = None
    ref: str | None = None


@dataclass
class LevoitData:
    """Coordinator data."""

    devices: dict[str, LevoitDevice] = field(default_factory=dict)
    heads: dict[str, ChannelHead] = field(default_factory=dict)


class LevoitEsphomeCoordinator(DataUpdateCoordinator[LevoitData]):
    """Joins Home Assistant's ESPHome devices, Device Builder configs and GitHub."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._heads: dict[str, ChannelHead] = {}
        self._heads_at: datetime | None = None
        self._facts: dict[str, ConfigFacts] = {}
        self._facts_task: asyncio.Task[None] | None = None
        self._tracked: frozenset[str] = frozenset()
        self._unsub_states: CALLBACK_TYPE | None = None
        # Device Builders before 2026.6 have no build queue: one compile at a time.
        self.build_lock = asyncio.Lock()

    @property
    def device_builder(self) -> DeviceBuilder | None:
        """Home Assistant's Device Builder connection."""
        return async_get_device_builder(self.hass)

    async def _async_update_data(self) -> LevoitData:
        builder = self.device_builder
        if builder is None:
            raise UpdateFailed("The ESPHome Device Builder add-on is not available")
        try:
            listing = await builder.api.get_devices()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Device Builder: {err}") from err
        configured: dict[str, dict[str, Any]] = {
            dev["name"]: dev for dev in listing.get("configured", []) if dev.get("name")
        }

        await self._async_refresh_heads()

        devices = self._collect_devices(configured)
        self._schedule_config_reads(builder, devices)
        self._track_version_entities(devices)
        return LevoitData(devices=devices, heads=dict(self._heads))

    async def _async_refresh_heads(self) -> None:
        now = dt_util.utcnow()
        if self._heads_at is not None and now - self._heads_at < GITHUB_INTERVAL:
            return
        try:
            self._heads = await async_fetch_heads(async_get_clientsession(self.hass))
        except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as err:
            # Keep the last known heads; try again on the next refresh.
            _LOGGER.warning("Could not read the latest versions from GitHub: %s", err)
            return
        self._heads_at = now

    @callback
    def _collect_devices(self, configured: dict[str, dict[str, Any]]) -> dict[str, LevoitDevice]:
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        devices: dict[str, LevoitDevice] = {}

        for entry in self.hass.config_entries.async_entries(ESPHOME_DOMAIN):
            name = entry.data.get("device_name")
            if not name:
                continue
            device = next(
                (
                    d
                    for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
                    if any(c[0] == dr.CONNECTION_NETWORK_MAC for c in d.connections)
                ),
                None,
            )
            if device is None:
                continue
            mac = next(c[1] for c in device.connections if c[0] == dr.CONNECTION_NETWORK_MAC)

            reported, version_entity_id = self._find_reported(ent_reg, device.id)
            config = configured.get(name)
            components = frozenset(
                COMPONENTS & set((config or {}).get("loaded_integrations") or [])
            )
            if not components and reported is None:
                continue  # not one of ours

            levoit_device = LevoitDevice(
                name=name,
                mac=mac,
                title=device.name_by_user or device.name or name,
                components=components,
                reported=reported,
                version_entity_id=version_entity_id,
            )
            if config is not None:
                levoit_device.configuration = config.get("configuration")
                levoit_device.esphome_deployed = config.get("deployed_version")
                levoit_device.esphome_current = config.get("current_version")
            if levoit_device.configuration and (
                facts := self._facts.get(levoit_device.configuration)
            ):
                levoit_device.model = facts.model
                levoit_device.channel = facts.channel
                levoit_device.ref = facts.ref
            devices[name] = levoit_device
        return devices

    def _find_reported(
        self, ent_reg: er.EntityRegistry, device_id: str
    ) -> tuple[Reported | None, str | None]:
        """The device's component version, from its `esp_version` text sensor.

        Matched by the state's format, so the sensor's name does not matter.
        ESPHome text sensors are `sensor` entities in Home Assistant.
        """
        for entity in er.async_entries_for_device(ent_reg, device_id):
            if entity.domain != Platform.SENSOR or entity.platform != ESPHOME_DOMAIN:
                continue
            state = self.hass.states.get(entity.entity_id)
            if state is None:
                continue
            if (reported := parse_reported(state.state)) is not None:
                return reported, entity.entity_id
        return None, None

    @callback
    def _schedule_config_reads(
        self, builder: DeviceBuilder, devices: dict[str, LevoitDevice]
    ) -> None:
        """Read model and channel of configs that are new, changed or stale."""
        if self._facts_task is not None and not self._facts_task.done():
            return
        now = dt_util.utcnow()
        stale = [
            (d.configuration, d.esphome_deployed)
            for d in devices.values()
            if d.configuration
            and (
                (facts := self._facts.get(d.configuration)) is None
                or now - facts.read_at >= CONFIG_INTERVAL
                or facts.deployed_version != d.esphome_deployed
            )
        ]
        if not stale:
            return
        self._facts_task = self.config_entry.async_create_background_task(
            self.hass, self._async_read_configs(builder, stale), f"{DOMAIN} config read"
        )

    async def _async_read_configs(
        self, builder: DeviceBuilder, stale: list[tuple[str, str | None]]
    ) -> None:
        """Run `esphome config` per config (in the Device Builder), one at a time."""
        changed = False
        for configuration, deployed in stale:
            try:
                config = await builder.api.get_config(configuration)
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Could not read %s: %s", configuration, err)
                continue
            # The resolved config contains secrets: keep only model and source.
            source = component_source(config or {})
            self._facts[configuration] = ConfigFacts(
                model=component_model(config or {}),
                channel=source[0] if source else None,
                ref=source[1] if source else None,
                read_at=dt_util.utcnow(),
                deployed_version=deployed,
            )
            changed = True
        if changed:
            await self.async_request_refresh()

    @callback
    def async_forget_config(self, configuration: str) -> None:
        """Read a config again on the next refresh (after a build)."""
        self._facts.pop(configuration, None)

    @callback
    def _track_version_entities(self, devices: dict[str, LevoitDevice]) -> None:
        """Refresh as soon as a device reports a new version (after an update)."""
        wanted = frozenset(d.version_entity_id for d in devices.values() if d.version_entity_id)
        if wanted == self._tracked:
            return
        if self._unsub_states is not None:
            self._unsub_states()
            self._unsub_states = None
        self._tracked = wanted
        if wanted:
            self._unsub_states = async_track_state_change_event(
                self.hass, list(wanted), self._async_version_changed
            )

    async def _async_version_changed(self, event: Event[EventStateChangedData]) -> None:
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Stop tracking states."""
        if self._unsub_states is not None:
            self._unsub_states()
            self._unsub_states = None
        await super().async_shutdown()
