"""LV600S discovery and mapping must work without pretending it is a fan."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.levoit_esphome.controls import (
    config_names,
    lv600s_stores_target,
    match_controls,
    page_supported,
)
from custom_components.levoit_esphome.versions import component_model, component_source
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import MAC, add_esphome_device
from .test_controls import _add_entities, _controls
from .test_init import _setup


def test_lv600s_source_model_and_names() -> None:
    config = {
        "lv600s_humidifier": {"model": "LV600S", "current_humidity": {"name": "Room humidity"}},
        "external_components": [
            {"source": "github://tuct/levoit@main", "components": ["lv600s_humidifier"]}
        ],
        "switch": [{"platform": "template", "id": "humidifier_power", "name": "Mist power"}],
        "number": [
            {"platform": "template", "id": "humidifier_target_preset", "name": "Desired humidity"}
        ],
        "api": {"encryption": {"key": "private-do-not-retain"}},
    }
    assert component_model(config) == "LV600S"
    assert component_source(config) == ("main", "main")
    assert config_names(config) == {
        "sensor.humidity": "Room humidity",
        "switch.power": "Mist power",
        "number.humidity_target_preset": "Desired humidity",
    }
    assert page_supported("LV600S", {"lv600s_humidifier"}, {})
    # A local/pinned owner build must never be offered an automatic upstream rewrite.
    config["external_components"] = [
        {
            "source": {"type": "local", "path": "local/components"},
            "components": ["lv600s_humidifier"],
        }
    ]
    assert component_source(config) == ("local", None)


@pytest.mark.usefixtures("patch_sources")
async def test_discovered_by_lv600s_model_only(
    hass: HomeAssistant, patch_sources: AsyncMock
) -> None:
    hass.config.components.add("esphome")
    add_esphome_device(hass, "living-humidifier", MAC, "Humidifier", None, model="LV600S")
    await _setup(hass)
    state = hass.states.get("sensor.humidifier_component_model")
    assert state is not None and state.state == "LV600S"


@pytest.mark.usefixtures("patch_sources")
async def test_existing_owner_control_names(hass: HomeAssistant) -> None:
    """The owner's existing names stay mapped without renaming entities or history."""
    hass.config.components.add("esphome")
    add_esphome_device(hass, "living-humidifier", MAC, "Humidifier", None, model="LV600S")
    ids = _add_entities(
        hass,
        MAC,
        {
            "switch.power": "Ein",
            "number.target": "Zielfeuchte",
            "number.warm": "Warmnebelstufe",
            "number.timer": "Timer Minuten",
            "sensor.timer_seconds": "Timer Restzeit",
            "binary_sensor.empty": "Wassermangel",
            "binary_sensor.removed": "Tank entfernt",
            "binary_sensor.fault": "Geraetefehler",
            "binary_sensor.connection": "MCU Verbindung",
            "fan.auxiliary": "Fan",
        },
    )
    device_id = er.async_get(hass).async_get(ids["switch.power"]).device_id
    found = match_controls(hass, device_id, "LV600S")
    assert found["switch.power"] == ids["switch.power"]
    assert found["number.humidity_target"] == ids["number.target"]
    assert found["number.warm_level"] == ids["number.warm"]
    assert found["number.timer"] == ids["number.timer"]
    assert found["sensor.timer_remaining_seconds"] == ids["sensor.timer_seconds"]
    assert found["binary_sensor.water_tank_empty"] == ids["binary_sensor.empty"]
    assert found["binary_sensor.tank_removed"] == ids["binary_sensor.removed"]
    assert found["binary_sensor.mcu_fault"] == ids["binary_sensor.fault"]
    assert found["binary_sensor.mcu_connection"] == ids["binary_sensor.connection"]
    assert "fan.fan" not in found
    assert match_controls(hass, device_id, "CORE600S")["fan.fan"] == ids["fan.auxiliary"]
    assert "switch.power" not in match_controls(hass, device_id, "CORE600S")

    numeric = ids["sensor.timer_seconds"]
    textual = _add_entities(hass, MAC, {"sensor.formatted_timer": "Timer Remaining"})
    formatted = textual["sensor.formatted_timer"]
    registry = er.async_get(hass)
    registry.async_update_entity(numeric, new_unique_id=f"{MAC}/0/sensor/Timer Restzeit")
    registry.async_update_entity(formatted, new_unique_id=f"{MAC}/0/text_sensor/Timer Remaining")
    assert match_controls(hass, device_id, "LV600S")["sensor.timer_remaining_seconds"] == formatted
    hass.states.async_set(numeric, "60")
    hass.states.async_set(formatted, "unavailable")
    assert match_controls(hass, device_id, "LV600S")["sensor.timer_remaining_seconds"] == numeric
    hass.states.async_set(formatted, "Unknown")
    assert match_controls(hass, device_id, "LV600S")["sensor.timer_remaining_seconds"] == formatted
    assert not lv600s_stores_target(hass, ids["number.target"], {})
    configured = {"number.humidity_target_preset": "Zielfeuchte"}
    assert lv600s_stores_target(hass, ids["number.target"], configured)
    assert (
        match_controls(hass, device_id, "LV600S", configured)["number.humidity_target"]
        == ids["number.target"]
    )


@pytest.mark.usefixtures("patch_sources")
@pytest.mark.parametrize(
    ("target_name", "is_preset"), [("Target Humidity Preset", True), ("Target Humidity", False)]
)
async def test_lv600s_panel_uses_esphome_entities(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, target_name: str, is_preset: bool
) -> None:
    """The device-controls API provides the panel's controls from the ESPHome entry."""
    hass.config.components.add("esphome")
    add_esphome_device(hass, "living-humidifier", MAC, "Humidifier", None, model="LV600S")
    names = {
        "switch.power": "Power",
        "switch.display": "Display",
        "select.humidifier_mode": "Operating Mode",
        "text_sensor.humidifier_mode_status": "Operating Mode Status",
        "number.humidity_target": target_name,
        "number.mist_level": "Mist Level",
        "number.warm_level": "Warm Level",
        "number.timer": "Timer (min)",
        "sensor.timer_remaining_seconds": "Timer Remaining",
        "text_sensor.timer_duration_initial": "Timer Duration",
        "sensor.humidity": "Humidity",
        "sensor.temperature": "Temperature",
        "binary_sensor.water_tank_empty": "Water Tank Empty",
        "binary_sensor.tank_removed": "Tank Removed",
        "binary_sensor.mcu_connection": "MCU Connection",
        "binary_sensor.mcu_fault": "MCU Fault",
        "binary_sensor.humidifying": "Humidifying",
        "binary_sensor.heating_enabled": "Heating Enabled",
    }
    entity_keys = {key: key.replace("text_sensor.", "sensor.", 1) for key in names}
    ids = _add_entities(hass, MAC, {entity_keys[key]: name for key, name in names.items()})

    await _setup(hass)
    client = await hass_ws_client(hass)
    page = await _controls(client, "living-humidifier")
    assert page["supported"] is True
    assert page["model"] == "LV600S"
    assert page["target_humidity_preset"] is is_preset
    assert page["controls"] == {key: ids[entity_keys[key]] for key in names}
    assert not hass.states.async_all("humidifier")
