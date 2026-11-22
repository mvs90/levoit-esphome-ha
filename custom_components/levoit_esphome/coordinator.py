"""Coordinator: which devices are ours, what they run, what is available."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field, replace
from datetime import datetime
import logging
import re
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import templates as tpl
from .const import (
    CHANNEL_STABLE,
    COMPONENTS,
    CONFIG_INTERVAL,
    DOMAIN,
    GITHUB_INTERVAL,
    KNOWN_MODELS,
    SCAN_INTERVAL,
)
from .device_builder import (
    DeviceBuilder,
    DeviceBuilderCommandError,
    async_get_device_builder,
    async_read_config,
    async_write_config,
)
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
    # builder file the config was made from; config_kind original / xiao_c3 / c3
    # for a template config, custom without one, None while unknown
    template: str | None = None
    config_kind: str | None = None


@dataclass
class LevoitDevice:
    """One ESPHome device that runs the levoit or philips component."""

    name: str
    mac: str
    title: str
    esphome_device_id: str
    components: frozenset[str]
    reported: Reported | None
    version_entity_id: str | None
    model_entity_id: str | None = None
    # the device's own filter-life sensor (ESPHome), shown by our Filter life
    filter_entity_id: str | None = None
    configuration: str | None = None
    esphome_deployed: str | None = None
    esphome_current: str | None = None
    model: str | None = None
    channel: str | None = None
    ref: str | None = None
    template: str | None = None
    config_kind: str | None = None


@dataclass
class _FoundSensors:
    """What a device's own ESPHome sensors tell."""

    reported: Reported | None = None
    version_entity_id: str | None = None
    model: str | None = None
    model_entity_id: str | None = None
    filter_entity_id: str | None = None


_PRE_FILTER = re.compile(r"\bpre[- ]?filter")


def _filter_score(entity: er.RegistryEntry, state: State | None) -> int | None:
    """How well a sensor fits as the device's filter life; None if it does not.

    The levoit / philips filter sensors report `%` with the `mdi:air-filter`
    icon by default; the name may be anything ("Filter %", "HEPA Filter" ...),
    so "filter" in the name also counts. With several, the main filter wins:
    HEPA over the pre-filter, the computed value over the MCU's.
    """
    attrs = state.attributes if state is not None else {}
    unit = entity.unit_of_measurement or attrs.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit != PERCENTAGE:
        return None
    icon = entity.icon or entity.original_icon or attrs.get(ATTR_ICON)
    name = " ".join(
        str(n) for n in (entity.name, entity.original_name, attrs.get(ATTR_FRIENDLY_NAME)) if n
    ).lower()
    if icon != "mdi:air-filter" and "filter" not in name:
        return None
    score = 0
    if "hepa" in name:
        score += 2
    if _PRE_FILTER.search(name):
        score -= 2
    if "mcu" in name:
        score -= 1
    return score


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
        self.templates: list[tpl.Template] = []
        self._facts: dict[str, ConfigFacts] = {}
        self._facts_task: asyncio.Task[None] | None = None
        # Channel per device name, for devices without a Device Builder config;
        # set (and restored after a restart) by the "Update channel" select.
        self._chosen_channels: dict[str, str] = {}
        # Version / model sensors found per device, kept while they are
        # unavailable (device restarting).
        self._sensors: dict[str, _FoundSensors] = {}
        self._tracked: frozenset[str] = frozenset()
        self._unsub_states: CALLBACK_TYPE | None = None
        # Device Builders before 2026.6 have no build queue: one compile at a time.
        self.build_lock = asyncio.Lock()
        self._building: set[str] = set()

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
        session = async_get_clientsession(self.hass)
        try:
            self._heads = await async_fetch_heads(session)
        except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as err:
            # Keep the last known heads; try again on the next refresh.
            _LOGGER.warning("Could not read the latest versions from GitHub: %s", err)
            return
        self._heads_at = now
        try:
            self.templates = await tpl.async_fetch_templates(session)
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Could not read the device templates from GitHub: %s", err)

    async def async_get_templates(self) -> list[tpl.Template]:
        """The device templates; fetched now if not loaded yet."""
        if not self.templates:
            self.templates = await tpl.async_fetch_templates(async_get_clientsession(self.hass))
        return self.templates

    async def async_refresh_from_template(self, builder: DeviceBuilder, configuration: str) -> bool:
        """Rewrite a template config from the newest builder file; True if it changed.

        Keeps the device's name, secret names (or inline values) and channel.
        A custom config is left alone. Written only if the file did not change
        in the meantime (the Device Builder checks `expected`).
        """
        text = await async_read_config(self.hass, builder, configuration)
        template = tpl.template_of(text, await self.async_get_templates())
        if template is None:
            return False
        source = await tpl.async_fetch_template_text(async_get_clientsession(self.hass), template)
        new = tpl.render(source, template, tpl.config_values(text))
        if new == text:
            return False
        await async_write_config(self.hass, builder, configuration, new, expected=text)
        return True

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

            found = self._scan_sensors(ent_reg, name, device.id)
            config = configured.get(name)
            components = frozenset(
                COMPONENTS & set((config or {}).get("loaded_integrations") or [])
            )
            if not components and found.reported is None and found.model is None:
                continue  # not one of ours

            levoit_device = LevoitDevice(
                name=name,
                mac=mac,
                title=device.name_by_user or device.name or name,
                esphome_device_id=device.id,
                components=components,
                reported=found.reported,
                version_entity_id=found.version_entity_id,
                model_entity_id=found.model_entity_id,
                filter_entity_id=found.filter_entity_id,
                model=found.model,
            )
            if config is not None:
                levoit_device.configuration = config.get("configuration")
                levoit_device.esphome_deployed = config.get("deployed_version")
                levoit_device.esphome_current = config.get("current_version")
            self._apply_facts(levoit_device)
            devices[name] = levoit_device
        return devices

    def _apply_facts(self, device: LevoitDevice) -> None:
        """Model and channel: from the config read, else the user's choice.

        A device without a Device Builder config has no `ref:` to read; its
        channel is the one picked in its "Update channel" select (default
        stable). The model then comes from its `model` text sensor.
        """
        if not device.configuration:
            device.channel = self._chosen_channels.get(device.name, CHANNEL_STABLE)
            return
        if facts := self._facts.get(device.configuration):
            device.model = facts.model or device.model
            device.channel = facts.channel
            device.ref = facts.ref
            device.template = facts.template
            device.config_kind = facts.config_kind

    @callback
    def async_choose_channel(self, name: str, channel: str) -> None:
        """Set the channel of a device without a Device Builder config."""
        self._chosen_channels[name] = channel
        if self.data is None or name not in self.data.devices:
            return
        self._async_reapply_facts()

    @callback
    def _async_reapply_facts(self) -> None:
        """Push the stored facts and choices to the current data, without a refresh."""
        devices = {n: replace(d) for n, d in self.data.devices.items()}
        for device in devices.values():
            self._apply_facts(device)
        self.async_set_updated_data(LevoitData(devices=devices, heads=self.data.heads))

    def can_set_channel(self, device: LevoitDevice) -> bool:
        """Without a config (the user's choice) or with a template config (its `ref:`).

        A custom config is the user's own file: its `ref:` is changed there.
        """
        return not device.configuration or device.template is not None

    async def async_set_channel(self, device: LevoitDevice, channel: str) -> None:
        """Switch a device to `channel`.

        Without a config this only changes what it is compared with. A template
        config gets its component `ref:` rewritten in the Device Builder (only
        if the file did not change meanwhile); the next install builds from
        the new channel.
        """
        if not device.configuration:
            self.async_choose_channel(device.name, channel)
            return
        builder = self.device_builder
        if builder is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_device_builder")
        if not self.can_set_channel(device):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="custom_channel")
        configuration = device.configuration
        try:
            text = await async_read_config(self.hass, builder, configuration)
            if tpl.template_of(text, await self.async_get_templates()) is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="custom_channel"
                )
            new = tpl.with_channel(text, channel)
            if new != text:
                await async_write_config(self.hass, builder, configuration, new, expected=text)
        except (
            DeviceBuilderCommandError,
            tpl.TemplateError,
            aiohttp.ClientError,
            TimeoutError,
        ) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="channel_failed",
                translation_placeholders={"configuration": configuration, "error": str(err)},
            ) from err
        # the ref is known now; no new `esphome config` run needed
        if (facts := self._facts.get(configuration)) is not None:
            self._facts[configuration] = replace(facts, channel=channel, ref=channel)
        if self.data is not None:
            self._async_reapply_facts()

    def _scan_sensors(self, ent_reg: er.EntityRegistry, name: str, device_id: str) -> _FoundSensors:
        """Version and model, from the device's `esp_version` and `model` sensors.

        Matched by their states (the version format, a known model name), so
        the sensors' names do not matter. ESPHome text sensors are `sensor`
        entities in Home Assistant.

        While the device restarts (after an update) its sensors are
        unavailable and match nothing. Then the sensors found before are kept,
        with their last values, so the device keeps its installed version and
        the sensors stay watched: the new version shows as soon as it is back.
        """
        found = _FoundSensors()
        best_filter: int | None = None
        for entity in er.async_entries_for_device(ent_reg, device_id):
            if entity.domain != Platform.SENSOR or entity.platform != ESPHOME_DOMAIN:
                continue
            state = self.hass.states.get(entity.entity_id)
            score = _filter_score(entity, state)
            if score is not None and (best_filter is None or score > best_filter):
                best_filter = score
                found.filter_entity_id = entity.entity_id
            if state is None:
                continue
            if found.reported is None and (reported := parse_reported(state.state)):
                found.reported = reported
                found.version_entity_id = entity.entity_id
            elif found.model is None and state.state in KNOWN_MODELS:
                found.model = state.state
                found.model_entity_id = entity.entity_id

        if (before := self._sensors.get(name)) is not None:
            if found.version_entity_id is None and self._offline(ent_reg, before.version_entity_id):
                found.reported = before.reported
                found.version_entity_id = before.version_entity_id
            if found.model_entity_id is None and self._offline(ent_reg, before.model_entity_id):
                found.model = before.model
                found.model_entity_id = before.model_entity_id
        self._sensors[name] = found
        return found

    def _offline(self, ent_reg: er.EntityRegistry, entity_id: str | None) -> bool:
        """The sensor still exists but has no value right now."""
        if entity_id is None or ent_reg.async_get(entity_id) is None:
            return False
        state = self.hass.states.get(entity_id)
        return state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)

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
        # Not eager: the task must not run inside the refresh that schedules it,
        # or that refresh's result would overwrite what the task applies.
        self._facts_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_read_configs(builder, stale),
            f"{DOMAIN} config read",
            eager_start=False,
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
            template, kind = await self._async_config_kind(builder, configuration)
            self._facts[configuration] = ConfigFacts(
                model=component_model(config or {}),
                channel=source[0] if source else None,
                ref=source[1] if source else None,
                read_at=dt_util.utcnow(),
                deployed_version=deployed,
                template=template,
                config_kind=kind,
            )
            changed = True
        if changed and self.data is not None:
            # Apply to the current data instead of a new refresh: no second
            # round of Device Builder and state lookups, and no refresh in
            # flight can overwrite it.
            self._async_reapply_facts()

    async def _async_config_kind(
        self, builder: DeviceBuilder, configuration: str
    ) -> tuple[str | None, str | None]:
        """Template file and kind of a config, from its YAML as written."""
        if not self.templates:
            return None, None
        try:
            text = await async_read_config(self.hass, builder, configuration)
        except DeviceBuilderCommandError as err:
            _LOGGER.debug("Could not read %s as written: %s", configuration, err)
            return None, None
        if (template := tpl.template_of(text, self.templates)) is None:
            return None, tpl.VARIANT_CUSTOM
        return template.file, template.variant

    @callback
    def async_forget_config(self, configuration: str) -> None:
        """Read a config again on the next refresh (after a build)."""
        self._facts.pop(configuration, None)

    def is_building(self, name: str) -> bool:
        """Whether a compile / upload of this device is running."""
        return name in self._building

    async def async_build(self, device: LevoitDevice, *, upload: bool) -> None:
        """Compile a device's config in the Device Builder; with `upload`, also install it.

        One build per device at a time. Installing first rewrites a template
        config from the newest builder file (a custom config is built as it
        is); compiling alone builds the config as it is now. A failed compile
        never uploads.
        """
        builder = self.device_builder
        if not device.configuration:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_configuration")
        if builder is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_device_builder")
        if device.name in self._building:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="already_building")
        configuration = device.configuration
        placeholders = {"configuration": configuration}
        lock: AbstractAsyncContextManager[Any] = (
            nullcontext() if getattr(builder, "supports_build_queue", False) else self.build_lock
        )

        self._building.add(device.name)
        self.async_update_listeners()
        try:
            if upload and device.template:
                try:
                    await self.async_refresh_from_template(builder, configuration)
                except (
                    DeviceBuilderCommandError,
                    tpl.TemplateError,
                    aiohttp.ClientError,
                    TimeoutError,
                ) as err:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="template_refresh_failed",
                        translation_placeholders={**placeholders, "error": str(err)},
                    ) from err
            async with lock:
                compiled = await builder.api.compile(configuration)
            if not compiled:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="compile_failed",
                    translation_placeholders=placeholders,
                )
            if upload and not await builder.api.upload(configuration, "OTA"):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="upload_failed",
                    translation_placeholders=placeholders,
                )
        finally:
            self._building.discard(device.name)
            if upload:
                self.async_forget_config(configuration)
            self.async_update_listeners()
            await self.async_request_refresh()

    @callback
    def _track_version_entities(self, devices: dict[str, LevoitDevice]) -> None:
        """Refresh as soon as a device reports a new version or model (after an update)."""
        wanted = frozenset(
            entity_id
            for d in devices.values()
            for entity_id in (d.version_entity_id, d.model_entity_id)
            if entity_id
        )
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
