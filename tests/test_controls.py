"""Device page: which entity is which setting, with and without a config."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.levoit_esphome.const import DOMAIN
from custom_components.levoit_esphome.controls import config_names
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import MAC, PURIFIER_CONFIG, FakeBuilder, add_esphome_device

NO_CONFIG_MAC = "de:ad:be:ef:00:02"


def _add_entities(hass: HomeAssistant, mac: str, entities: dict[str, str]) -> dict[str, str]:
    """ESPHome entities on the device with that MAC: 'domain.object_id' -> name."""
    device = next(
        d
        for d in dr.async_get(hass).devices.values()
        if (dr.CONNECTION_NETWORK_MAC, mac) in d.connections
    )
    entry_id = next(iter(device.config_entries))
    entry = hass.config_entries.async_get_entry(entry_id)
    ids = {}
    for key, name in entities.items():
        domain, object_id = key.split(".", 1)
        entity = er.async_get(hass).async_get_or_create(
            domain,
            "esphome",
            f"{mac}-{domain}-{object_id}",
            device_id=device.id,
            config_entry=entry,
            original_name=name,
            suggested_object_id=object_id,
        )
        ids[key] = entity.entity_id
    return ids


async def _setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Levoit ESPHome", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def _controls(client: Any, name: str) -> dict[str, Any]:
    await client.send_json_auto_id({"type": "levoit_esphome/device_controls", "name": name})
    msg = await client.receive_json()
    assert msg["success"], msg
    return msg["result"]


def test_config_names() -> None:
    """Names of levoit entities only, per key; the fan has no type."""
    config = {
        "fan": [{"platform": "levoit", "name": "Purifier"}],
        "select": [
            {"platform": "levoit", "type": "auto_mode", "name": "Auto"},
            {"platform": "template", "name": "Other"},
        ],
        "text_sensor": [{"platform": "levoit", "type": "esp_version", "name": "ESP Version"}],
        "api": {"encryption": {"key": "secret"}},
    }
    assert config_names(config) == {
        "fan.fan": "Purifier",
        "select.auto_mode": "Auto",
        "text_sensor.esp_version": "ESP Version",
    }


@pytest.mark.usefixtures("patch_sources")
async def test_without_config(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    """No Device Builder config: the default names, older spellings and prefixes match."""
    hass.config.components.add("esphome")
    add_esphome_device(
        hass, "office-purifier", NO_CONFIG_MAC, "Office", "1.7.3+abcdef1 esphome", model="CORE300S"
    )
    ids = _add_entities(
        hass,
        NO_CONFIG_MAC,
        {
            "fan.fan": "Fan",
            "select.auto_mode": "Auto Mode",
            "number.timer": "Timer (min)",
            "sensor.pm25": "AQ - PM 2.5",
            # an older spelling, and an old config's device-name prefix
            "button.reset": "Reset Filter Stats",
            "switch.display": "office-purifier Display",
            "switch.other": "Something Else",
        },
    )
    await _setup(hass)
    client = await hass_ws_client(hass)

    result = await _controls(client, "office-purifier")
    assert result["supported"] is True
    assert result["model"] == "CORE300S"
    assert result["from_config"] is False
    controls = result["controls"]
    assert controls["fan.fan"] == ids["fan.fan"]
    assert controls["select.auto_mode"] == ids["select.auto_mode"]
    assert controls["number.timer"] == ids["number.timer"]
    assert controls["sensor.pm25"] == ids["sensor.pm25"]
    assert controls["button.reset_filter_stats"] == ids["button.reset"]
    assert controls["switch.display"] == ids["switch.display"]
    assert ids["switch.other"] not in controls.values()


@pytest.mark.usefixtures("patch_sources")
async def test_eleva_aqi(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    """On the Eleva "AQI" is the index and "Air Quality Level" the level."""
    hass.config.components.add("esphome")
    add_esphome_device(
        hass, "eleva", NO_CONFIG_MAC, "Eleva", "1.7.3+abcdef1 esphome", model="ELEVA300X"
    )
    ids = _add_entities(
        hass, NO_CONFIG_MAC, {"sensor.aqi": "AQI", "sensor.level": "Air Quality Level"}
    )
    await _setup(hass)
    client = await hass_ws_client(hass)

    controls = (await _controls(client, "eleva"))["controls"]
    assert controls["sensor.aqi_index"] == ids["sensor.aqi"]
    assert controls["sensor.aqi"] == ids["sensor.level"]


@pytest.mark.usefixtures("esphome_devices", "patch_sources")
async def test_names_from_config(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, builder: FakeBuilder
) -> None:
    """With a config, its names win: renamed entities are found too."""
    builder.api.configs["bedroom-purifier.yaml"] = {
        **PURIFIER_CONFIG,
        "select": [{"platform": "levoit", "type": "auto_mode", "name": "Smart Mode"}],
    }
    ids = _add_entities(hass, MAC, {"select.smart_mode": "Smart Mode", "fan.fan": "Fan"})
    await _setup(hass)
    client = await hass_ws_client(hass)

    result = await _controls(client, "bedroom-purifier")
    assert result["from_config"] is True
    assert result["controls"]["select.auto_mode"] == ids["select.smart_mode"]
    assert result["controls"]["fan.fan"] == ids["fan.fan"]


@pytest.mark.usefixtures("patch_sources")
async def test_unsupported_model(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    """Models without a page yet (Sprout here) say so; unknown device names fail."""
    hass.config.components.add("esphome")
    add_esphome_device(
        hass, "sprout", NO_CONFIG_MAC, "Sprout", "1.7.3+abcdef1 esphome", model="SPROUT"
    )
    _add_entities(hass, NO_CONFIG_MAC, {"fan.fan": "Fan"})
    await _setup(hass)
    client = await hass_ws_client(hass)

    assert (await _controls(client, "sprout"))["supported"] is False
    await client.send_json_auto_id({"type": "levoit_esphome/device_controls", "name": "nope"})
    msg = await client.receive_json()
    assert msg["error"]["code"] == "not_found"


@pytest.mark.usefixtures("esphome_devices", "patch_sources")
async def test_admins_only(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str
) -> None:
    """Like the other panel commands: admins only."""
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "levoit_esphome/device_controls", "name": "x"})
    msg = await client.receive_json()
    assert msg["error"]["code"] == "unauthorized"
