"""Setup, entities and install, with a stub Device Builder and GitHub."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.levoit_esphome.const import DOMAIN
from homeassistant.components.update import (
    ATTR_INSTALLED_VERSION,
    ATTR_LATEST_VERSION,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import MAC, OTHER_MAC, FakeBuilder, add_esphome_device

UPDATE = "update.bedroom_purifier_component_firmware"
BUTTON = "button.bedroom_purifier_compile_firmware"
SELECT = "select.bedroom_purifier_update_channel"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Levoit ESPHome", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


@pytest.mark.usefixtures("esphome_devices")
async def test_setup_finds_our_device(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """The purifier gets entities on its own device; the other device none."""
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get(UPDATE)
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INSTALLED_VERSION] == "1.7.0+10361cc"
    assert state.attributes[ATTR_LATEST_VERSION] == "1.8.0+abcdef1"

    assert (
        hass.states.get("sensor.bedroom_purifier_installed_component_version").state
        == "1.7.0+10361cc"
    )
    assert (
        hass.states.get("sensor.bedroom_purifier_latest_component_version").state == "1.8.0+abcdef1"
    )
    assert hass.states.get("sensor.bedroom_purifier_component_model").state == "CORE300S"
    assert hass.states.get("sensor.bedroom_purifier_firmware_channel").state == "stable"
    assert (
        hass.states.get("sensor.bedroom_purifier_device_builder_config").state
        == "bedroom-purifier.yaml"
    )

    # Our own device, named like the purifier, sharing its MAC (Home Assistant
    # lists the ESPHome device as linked through that)
    dev_reg = dr.async_get(hass)
    ours = dev_reg.async_get_device_by_identifier((DOMAIN, MAC), entry.entry_id)
    assert ours is not None
    assert ours.name == "Bedroom purifier"
    assert (dr.CONNECTION_NETWORK_MAC, MAC) in ours.connections
    assert ours.via_device_id is None
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get(UPDATE).device_id == ours.id

    # The unrelated device gets nothing
    assert dev_reg.async_get_device_by_identifier((DOMAIN, OTHER_MAC), entry.entry_id) is None
    assert len(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)) == 1

    # Only our config was read, once
    assert builder.api.get_config_calls == ["bedroom-purifier.yaml"]


@pytest.mark.usefixtures("esphome_devices")
async def test_no_secrets_kept(hass: HomeAssistant, patch_sources: AsyncMock) -> None:
    """The resolved config (with its API key) is not kept anywhere."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    assert "c2VjcmV0" not in repr(coordinator.data)
    assert "c2VjcmV0" not in repr(coordinator._facts)


async def test_up_to_date(
    hass: HomeAssistant, patch_sources: AsyncMock, esphome_devices: dict
) -> None:
    """At the channel head: no update."""
    hass.states.async_set(esphome_devices["purifier"], "1.8.0+abcdef1 esphome")
    await _setup(hass)
    state = hass.states.get(UPDATE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_INSTALLED_VERSION] == "1.8.0+abcdef1"


async def test_new_version_reported_refreshes(
    hass: HomeAssistant, patch_sources: AsyncMock, esphome_devices: dict
) -> None:
    """After an update the device reports the new version; the entity follows."""
    await _setup(hass)
    assert hass.states.get(UPDATE).state == STATE_ON
    hass.states.async_set(esphome_devices["purifier"], "1.8.0+abcdef1 esphome")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(UPDATE).state == STATE_OFF


async def test_restart_after_update(
    hass: HomeAssistant, patch_sources: AsyncMock, esphome_devices: dict
) -> None:
    """While the device restarts its sensor is unavailable: keep the version,
    keep watching, and pick up the new version when it is back."""
    await _setup(hass)
    assert hass.states.get(UPDATE).attributes[ATTR_INSTALLED_VERSION] == "1.7.0+10361cc"

    hass.states.async_set(esphome_devices["purifier"], STATE_UNAVAILABLE)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(UPDATE)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INSTALLED_VERSION] == "1.7.0+10361cc"

    hass.states.async_set(esphome_devices["purifier"], "1.8.0+abcdef1 esphome")
    # past the refresh debouncer's cooldown
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(UPDATE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_INSTALLED_VERSION] == "1.8.0+abcdef1"


async def test_drops_via_device(
    hass: HomeAssistant, patch_sources: AsyncMock, esphome_devices: dict
) -> None:
    """The "connected via" link of the first version is removed."""
    entry = MockConfigEntry(domain=DOMAIN, title="Levoit ESPHome", data={})
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    esphome_device = next(
        d
        for e in hass.config_entries.async_entries("esphome")
        for d in dr.async_entries_for_config_entry(dev_reg, e.entry_id)
        if (dr.CONNECTION_NETWORK_MAC, MAC) in d.connections
    )
    ours = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, MAC)},
        via_device_id=esphome_device.id,
    )
    assert ours.via_device_id == esphome_device.id

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert dev_reg.async_get(ours.id).via_device_id is None


@pytest.mark.usefixtures("esphome_devices")
async def test_install(hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder) -> None:
    """Install compiles, then uploads over the air."""
    await _setup(hass)
    await hass.services.async_call("update", "install", {ATTR_ENTITY_ID: UPDATE}, blocking=True)
    builder.api.compile.assert_awaited_once_with("bedroom-purifier.yaml")
    builder.api.upload.assert_awaited_once_with("bedroom-purifier.yaml", "OTA")


@pytest.mark.usefixtures("esphome_devices")
async def test_install_compile_fails(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """A failed build never uploads."""
    builder.api.compile.return_value = False
    await _setup(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("update", "install", {ATTR_ENTITY_ID: UPDATE}, blocking=True)
    builder.api.upload.assert_not_awaited()
    assert hass.states.get(UPDATE).attributes["in_progress"] is False


@pytest.mark.usefixtures("esphome_devices")
async def test_compile_button(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """The button compiles without uploading."""
    await _setup(hass)
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: BUTTON}, blocking=True)
    builder.api.compile.assert_awaited_once_with("bedroom-purifier.yaml")
    builder.api.upload.assert_not_awaited()


@pytest.mark.usefixtures("esphome_devices")
async def test_github_unreachable(hass: HomeAssistant, patch_sources: AsyncMock) -> None:
    """Without GitHub the device is listed; whether it is behind is unknown."""
    patch_sources.side_effect = TimeoutError
    await _setup(hass)
    state = hass.states.get(UPDATE)
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_INSTALLED_VERSION] == "1.7.0+10361cc"
    assert state.attributes[ATTR_LATEST_VERSION] is None
    assert (
        hass.states.get("sensor.bedroom_purifier_latest_component_version").state == STATE_UNKNOWN
    )


async def test_without_device_builder_config(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """No config: channel from the select (default stable), model from the sensor."""
    hass.config.components.add("esphome")
    builder.api.configured = []  # nothing in the Device Builder
    version_entity = add_esphome_device(
        hass,
        "bedroom-purifier",
        MAC,
        "Bedroom purifier",
        "1.7.0+10361cc esphome",
        model="EVERESTAIR",
    )
    await _setup(hass)

    assert hass.states.get(SELECT).state == "stable"
    assert hass.states.get("sensor.bedroom_purifier_firmware_channel").state == "stable"
    assert hass.states.get("sensor.bedroom_purifier_component_model").state == "EVERESTAIR"
    assert builder.api.get_config_calls == []

    # stable: 1.8.0 is out, the device runs 1.7.0
    state = hass.states.get(UPDATE)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_LATEST_VERSION] == "1.8.0+abcdef1"
    # ... but installing needs a config
    assert not state.attributes[ATTR_SUPPORTED_FEATURES] & UpdateEntityFeature.INSTALL
    assert hass.states.get(BUTTON).state == STATE_UNAVAILABLE

    # main: the commit decides
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SELECT, "option": "main"}, blocking=True
    )
    assert hass.states.get(SELECT).state == "main"
    assert hass.states.get(UPDATE).state == STATE_ON
    hass.states.async_set(version_entity, "1.8.0+1234567 esphome")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(UPDATE).state == STATE_OFF

    # a main build is not behind stable
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SELECT, "option": "stable"}, blocking=True
    )
    assert hass.states.get(UPDATE).state == STATE_OFF


@pytest.mark.usefixtures("esphome_devices")
async def test_select_unavailable_with_config(
    hass: HomeAssistant, patch_sources: AsyncMock
) -> None:
    """With a Device Builder config the ref decides; the select is off."""
    await _setup(hass)
    assert hass.states.get(SELECT).state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bedroom_purifier_firmware_channel").state == "stable"


async def test_found_by_model_sensor_only(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """A model sensor alone (no version yet) is enough to be listed."""
    hass.config.components.add("esphome")
    builder.api.configured = []
    add_esphome_device(hass, "bedroom-purifier", MAC, "Bedroom purifier", None, model="CORE300S")
    await _setup(hass)
    assert hass.states.get("sensor.bedroom_purifier_component_model").state == "CORE300S"
    assert hass.states.get(UPDATE).state == STATE_UNKNOWN  # no installed version


@pytest.mark.usefixtures("esphome_devices")
async def test_setup_retries_without_device_builder(hass: HomeAssistant) -> None:
    """No Device Builder yet: retry later."""
    from unittest.mock import patch  # noqa: PLC0415

    with patch(
        "custom_components.levoit_esphome.coordinator.async_get_device_builder",
        return_value=None,
    ):
        entry = MockConfigEntry(domain=DOMAIN, title="Levoit ESPHome", data={})
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.SETUP_RETRY


FILTER = "sensor.bedroom_purifier_filter_life"


async def test_filter_life(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """The purifier's filter % shows on our device and follows it."""
    hass.config.components.add("esphome")
    add_esphome_device(
        hass,
        "bedroom-purifier",
        MAC,
        "Bedroom purifier",
        "1.7.0+10361cc esphome",
        filters={"Filter %": "83"},
    )
    await _setup(hass)
    assert float(hass.states.get(FILTER).state) == 83

    hass.states.async_set(
        "sensor.bedroom_purifier_filter_0",
        "82",
        {"unit_of_measurement": "%", "friendly_name": "Filter %"},
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(FILTER).state) == 82


async def test_filter_life_prefers_hepa(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """Philips: HEPA filter over the pre-filter."""
    hass.config.components.add("esphome")
    add_esphome_device(
        hass,
        "bedroom-purifier",
        MAC,
        "Bedroom purifier",
        "1.7.0+10361cc esphome",
        filters={"Pre-filter": "40", "HEPA Filter": "90"},
    )
    await _setup(hass)
    assert float(hass.states.get(FILTER).state) == 90


@pytest.mark.usefixtures("esphome_devices")
async def test_no_filter_sensor(hass: HomeAssistant, patch_sources: AsyncMock) -> None:
    """Without a filter sensor on the device: unavailable."""
    await _setup(hass)
    assert hass.states.get(FILTER).state == STATE_UNAVAILABLE
