"""Add device (config subentry) and template refresh on install."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.levoit_esphome.const import DOMAIN
from custom_components.levoit_esphome.templates import (
    MARKER_PREFIX,
    ConfigValues,
    Value,
    config_values,
    render,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import BUILDER_TEXT, EVEREST_C3, MAC, FakeBuilder, add_esphome_device

UPDATE = "update.bedroom_purifier_component_firmware"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Levoit ESPHome", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def _start(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )


async def _step(
    hass: HomeAssistant, result: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    return await hass.config_entries.subentries.async_configure(result["flow_id"], data)


@pytest.mark.usefixtures("esphome_devices")
async def test_new_device(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """Model, variant, name, channel: config and generated keys in the Device Builder."""
    entry = await _setup(hass)
    result = await _start(hass, entry)
    # every known device has a config: straight to the model
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "new"

    result = await _step(hass, result, {"model": "EVERESTAIR"})
    assert result["step_id"] == "variant"
    result = await _step(hass, result, {"variant": "xiao_c3"})
    assert result["step_id"] == "details"
    schema = {str(key): key for key in result["data_schema"].schema}
    assert schema["name"].default() == "levoit-everest-air-c3"

    result = await _step(hass, result, {"name": "levoit-everest-air-c3", "channel": "main"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "levoit-everest-air-c3"
    assert result["description_placeholders"]["builder_url"] == "/app/5c53de3b_esphome"

    text = builder.files.configs["levoit-everest-air-c3.yaml"]
    assert text.startswith(f"{MARKER_PREFIX}{EVEREST_C3.file}\n")
    assert config_values(text) == ConfigValues(
        name="levoit-everest-air-c3",
        api_key=Value(secret="levoit_everest_air_c3_api_key"),
        ota_password=Value(secret="levoit_everest_air_c3_ota_password"),
        channel="main",
    )
    secrets = builder.files.secrets
    assert len(secrets["levoit_everest_air_c3_api_key"]) == 44
    assert len(secrets["levoit_everest_air_c3_ota_password"]) == 32
    assert secrets["wifi_password"] == "wifi-pw"  # untouched


@pytest.mark.usefixtures("esphome_devices")
async def test_new_device_errors(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """Bad or taken name, missing Wi-Fi secrets, an existing secret."""
    entry = await _setup(hass)
    result = await _start(hass, entry)
    result = await _step(hass, result, {"model": "EVERESTAIR"})
    result = await _step(hass, result, {"variant": "original"})

    result = await _step(hass, result, {"name": "My Purifier", "channel": "stable"})
    assert result["errors"] == {"name": "invalid_name"}
    result = await _step(hass, result, {"name": "bedroom-purifier", "channel": "stable"})
    assert result["errors"] == {"name": "name_taken"}

    del builder.files.secrets["wifi_password"]
    result = await _step(hass, result, {"name": "living-room-air", "channel": "stable"})
    assert result["errors"] == {"base": "missing_wifi_secrets"}
    assert result["description_placeholders"]["missing"] == "wifi_password"

    builder.files.secrets["wifi_password"] = "wifi-pw"
    builder.files.secrets["living_room_air_api_key"] = "already there"
    result = await _step(hass, result, {"name": "living-room-air", "channel": "stable"})
    assert result["errors"] == {"base": "secret_exists"}
    assert builder.files.secrets["living_room_air_api_key"] == "already there"
    assert "living-room-air.yaml" not in builder.files.configs


async def test_existing_device(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """A device without a config keeps its name, API key and OTA password."""
    hass.config.components.add("esphome")
    builder.api.configured = []
    builder.files.configs.clear()  # no config at all, as for a device without one
    add_esphome_device(
        hass,
        "bedroom-purifier",
        MAC,
        "Bedroom purifier",
        "1.7.0 esphome",
        model="EVERESTAIR",
        noise_psk="ZXhpc3Rpbmcta2V5LW9mLXRoZS1kZXZpY2UtMzJieXRlcyE=",
    )
    entry = await _setup(hass)

    result = await _start(hass, entry)
    assert result["type"] is FlowResultType.MENU
    result = await _step(hass, result, {"next_step_id": "existing"})
    result = await _step(hass, result, {"device": "bedroom-purifier"})
    # model known from the device's model sensor: straight to the variant
    assert result["step_id"] == "variant"
    result = await _step(hass, result, {"variant": "xiao_c3"})
    assert result["step_id"] == "details_existing"
    # the form says which secret the key from Home Assistant goes into
    assert result["description_placeholders"]["api_secret"] == "bedroom_purifier_api_key"
    result = await _step(hass, result, {"channel": "stable", "ota_password": "its-ota-pw"})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    text = builder.files.configs["bedroom-purifier.yaml"]
    assert config_values(text).name == "bedroom-purifier"
    secrets = builder.files.secrets
    assert secrets["bedroom_purifier_api_key"] == "ZXhpc3Rpbmcta2V5LW9mLXRoZS1kZXZpY2UtMzJieXRlcyE="
    assert secrets["bedroom_purifier_ota_password"] == "its-ota-pw"

    # the device and its entities move under the new sub-entry (one device, no copy)
    await hass.async_block_till_done(wait_background_tasks=True)
    subentry = next(iter(entry.subentries.values()))
    assert subentry.unique_id == "bedroom-purifier"
    dev_reg = dr.async_get(hass)
    ours = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert len(ours) == 1
    assert ours[0].config_subentry_id == subentry.subentry_id
    entities = er.async_entries_for_device(er.async_get(hass), ours[0].id)
    assert entities
    assert all(e.config_subentry_id == subentry.subentry_id for e in entities)


async def test_existing_device_without_keys(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """No encryption and no OTA password stay that way."""
    hass.config.components.add("esphome")
    builder.api.configured = []
    builder.files.configs.clear()  # no config at all, as for a device without one
    add_esphome_device(
        hass, "bedroom-purifier", MAC, "Bedroom purifier", "1.7.0 esphome", model="EVERESTAIR"
    )
    entry = await _setup(hass)
    result = await _start(hass, entry)
    result = await _step(hass, result, {"next_step_id": "existing"})
    result = await _step(hass, result, {"device": "bedroom-purifier"})
    result = await _step(hass, result, {"variant": "xiao_c3"})
    result = await _step(hass, result, {"channel": "stable"})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    values = config_values(builder.files.configs["bedroom-purifier.yaml"])
    assert values.api_key is None
    assert values.ota_password is None
    assert set(builder.files.secrets) == {"wifi_ssid", "wifi_password", "wifi_ap_password"}


@pytest.mark.usefixtures("esphome_devices")
async def test_install_refreshes_template_config(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """A template config is rewritten from the newest builder file, then built."""
    values = ConfigValues(
        name="bedroom-purifier",
        api_key=Value(secret="bedroom_purifier_api_key"),
        ota_password=Value(secret="bedroom_purifier_ota_password"),
        channel="stable",
    )
    old = render(BUILDER_TEXT.replace("level: DEBUG", "level: INFO"), EVEREST_C3, values)
    builder.files.configs["bedroom-purifier.yaml"] = old
    await _setup(hass)
    assert hass.states.get("sensor.bedroom_purifier_config_type").state == "xiao_c3"

    await hass.services.async_call("update", "install", {ATTR_ENTITY_ID: UPDATE}, blocking=True)

    new = builder.files.configs["bedroom-purifier.yaml"]
    assert new == render(BUILDER_TEXT, EVEREST_C3, values)
    assert config_values(new) == values  # keeps name, secrets, channel
    builder.api.compile.assert_awaited_once_with("bedroom-purifier.yaml")


@pytest.mark.usefixtures("esphome_devices")
async def test_install_keeps_custom_config(
    hass: HomeAssistant, patch_sources: AsyncMock, builder: FakeBuilder
) -> None:
    """A custom config is never rewritten; only built."""
    await _setup(hass)
    assert hass.states.get("sensor.bedroom_purifier_config_type").state == "custom"
    await hass.services.async_call("update", "install", {ATTR_ENTITY_ID: UPDATE}, blocking=True)
    assert builder.files.writes == []
    builder.api.compile.assert_awaited_once_with("bedroom-purifier.yaml")
