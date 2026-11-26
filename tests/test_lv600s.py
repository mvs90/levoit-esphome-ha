"""LV600S discovery and mapping must work without pretending it is a fan."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.levoit_esphome.controls import config_names, match_controls, page_supported
from custom_components.levoit_esphome.versions import component_model, component_source
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import MAC, add_esphome_device
from .test_controls import _add_entities
from .test_init import _setup


def test_lv600s_source_model_and_names() -> None:
    config = {
        "lv600s_humidifier": {"model": "LV600S", "current_humidity": {"name": "Room humidity"}},
        "external_components": [
            {"source": "github://tuct/levoit@main", "components": ["lv600s_humidifier"]}
        ],
        "switch": [{"platform": "template", "id": "humidifier_power", "name": "Mist power"}],
        "api": {"encryption": {"key": "private-do-not-retain"}},
    }
    assert component_model(config) == "LV600S"
    assert component_source(config) == ("main", "main")
    assert config_names(config) == {
        "sensor.humidity": "Room humidity",
        "switch.power": "Mist power",
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
    dr.async_get(hass).async_update_device(
        device_id, sw_version="1.2.07-target-preset (ESPHome 2026.11.1)"
    )
    assert match_controls(hass, device_id, "LV600S")["sensor.timer_remaining_seconds"] == formatted


@pytest.mark.usefixtures("patch_sources")
async def test_native_lv600s_humidifier(hass: HomeAssistant) -> None:
    """Expose real settings and hide diagnostic states from the supported modes."""
    hass.config.components.add("esphome")
    add_esphome_device(hass, "living-humidifier", MAC, "Humidifier", None, model="LV600S")
    ids = _add_entities(
        hass,
        MAC,
        {
            "switch.power": "Ein",
            "select.mode": "Betriebsmodus",
            "number.target": "Zielfeuchte",
            "sensor.humidity": "Luftfeuchtigkeit",
            "binary_sensor.empty": "Wassermangel",
            "binary_sensor.connection": "MCU Verbindung",
            "binary_sensor.active": "Befeuchtet",
        },
    )
    mode_attrs = {"options": ["Manuell", "Feuchte", "Schlaf", "Auto (Original)", "Unbekannt"]}
    for key, value in {
        "switch.power": "off",
        "number.target": "unknown",
        "sensor.humidity": "42",
        "binary_sensor.empty": "off",
        "binary_sensor.connection": "on",
        "binary_sensor.active": "off",
    }.items():
        hass.states.async_set(ids[key], value)
    hass.states.async_set(ids["select.mode"], "Manuell", mode_attrs)

    calls = []

    async def power(call):
        calls.append(call.service)
        hass.states.async_set(ids["switch.power"], "on" if call.service == "turn_on" else "off")

    async def mode(call):
        assert hass.states.get(ids["switch.power"]).state == "on"
        calls.append(call.data["option"])
        hass.states.async_set(ids["select.mode"], call.data["option"], mode_attrs)

    async def target(call):
        assert hass.states.get(ids["select.mode"]).state == "Feuchte"
        calls.append(call.data["value"])
        hass.states.async_set(ids["number.target"], "53")

    await _setup(hass)
    hass.services.async_register("switch", "turn_on", power)
    hass.services.async_register("switch", "turn_off", power)
    hass.services.async_register("select", "select_option", mode)
    hass.services.async_register("number", "set_value", target)
    (entity,) = hass.states.async_all("humidifier")
    entity_id = entity.entity_id
    assert entity.state == "off"
    assert entity.attributes["device_class"] == "humidifier"
    assert entity.attributes["available_modes"] == ["manual", "auto", "sleep"]
    assert entity.attributes["current_humidity"] == 42

    await hass.services.async_call(
        "humidifier", "set_humidity", {"entity_id": entity_id, "humidity": 53}, blocking=True
    )
    await hass.async_block_till_done()
    assert calls == ["turn_on", "Feuchte", 53]
    assert hass.states.get(entity_id).state == "on"
    assert hass.states.get(entity_id).attributes["humidity"] == 53
    assert hass.states.get(entity_id).attributes["mode"] == "auto"

    hass.states.async_set(ids["select.mode"], "Auto (Original)", mode_attrs)
    hass.states.async_set(ids["binary_sensor.active"], "on")
    await hass.async_block_till_done()
    attributes = hass.states.get(entity_id).attributes
    assert attributes.get("mode") is None
    assert attributes["reported_mode"] == "original_auto"
    assert attributes["action"] == "humidifying"

    hass.states.async_set(ids["binary_sensor.empty"], "on")
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            "humidifier", "set_mode", {"entity_id": entity_id, "mode": "sleep"}, blocking=True
        )
    assert error.value.translation_key == "lv600s_unready"
    assert calls == ["turn_on", "Feuchte", 53]

    await hass.services.async_call(
        "humidifier", "turn_off", {"entity_id": entity_id}, blocking=True
    )
    assert calls[-1] == "turn_off"


@pytest.mark.usefixtures("patch_sources")
async def test_native_lv600s_forwards_presets_without_changing_mode(hass: HomeAssistant) -> None:
    hass.config.components.add("esphome")
    add_esphome_device(hass, "living-humidifier", MAC, "Humidifier", None, model="LV600S")
    ids = _add_entities(
        hass,
        MAC,
        {
            "switch.power": "Ein",
            "select.mode": "Betriebsmodus",
            "number.target": "Zielfeuchte",
            "binary_sensor.empty": "Wassermangel",
        },
    )
    device_id = er.async_get(hass).async_get(ids["switch.power"]).device_id
    dr.async_get(hass).async_update_device(
        device_id, sw_version="1.2.07-target-preset (ESPHome 2026.11.1)"
    )
    hass.states.async_set(ids["switch.power"], "on")
    hass.states.async_set(ids["select.mode"], "Manuell", {"options": ["Manuell", "Auto", "Schlaf"]})
    hass.states.async_set(ids["binary_sensor.empty"], "off")
    await _setup(hass)
    (entity,) = hass.states.async_all("humidifier")
    calls = []

    async def save_target(call):
        calls.append(call.data["value"])
        hass.states.async_set(ids["number.target"], "58")

    hass.services.async_register("number", "set_value", save_target)
    await hass.services.async_call(
        "humidifier", "set_humidity", {"entity_id": entity.entity_id, "humidity": 58}, blocking=True
    )
    await hass.async_block_till_done()
    assert calls == [58]
    assert hass.states.get(ids["select.mode"]).state == "Manuell"
    assert hass.states.get(entity.entity_id).attributes["humidity"] == 58


@pytest.mark.usefixtures("patch_sources")
@pytest.mark.parametrize("power_name", ["Ein", "Luftbefeuchter", "Humidifier"])
@pytest.mark.parametrize("reported_auto", ["Auto", "Humidity"])
async def test_native_lv600s_mode_status(
    hass: HomeAssistant, power_name: str, reported_auto: str
) -> None:
    """Confirm writes from the MCU status when the selector retains an old option."""
    hass.config.components.add("esphome")
    add_esphome_device(hass, "living-humidifier", MAC, "Humidifier", None, model="LV600S")
    ids = _add_entities(
        hass,
        MAC,
        {
            "switch.power": power_name,
            "select.mode": "Betriebsmodus",
            "sensor.mode_status": "Betriebsmodus Status",
            "number.target": "Zielfeuchte",
        },
    )
    hass.states.async_set(ids["switch.power"], "on")
    hass.states.async_set(ids["select.mode"], "Auto", {"options": ["Manuell", "Auto", "Schlaf"]})
    hass.states.async_set(ids["sensor.mode_status"], "Auto (Original)")
    hass.states.async_set(ids["number.target"], "50")

    calls = []

    async def mode(call):
        assert call.data["option"] == "Auto"
        calls.append(call.data["option"])
        hass.states.async_set(ids["sensor.mode_status"], reported_auto)

    async def target(call):
        assert hass.states.get(ids["sensor.mode_status"]).state == reported_auto
        calls.append(call.data["value"])
        hass.states.async_set(ids["number.target"], str(call.data["value"]))

    await _setup(hass)
    hass.services.async_register("select", "select_option", mode)
    hass.services.async_register("number", "set_value", target)
    (entity,) = hass.states.async_all("humidifier")
    assert entity.attributes["available_modes"] == ["manual", "auto", "sleep"]
    assert entity.attributes["reported_mode"] == "original_auto"
    assert entity.attributes.get("mode") is None
    await hass.services.async_call(
        "humidifier",
        "set_humidity",
        {"entity_id": entity.entity_id, "humidity": 55},
        blocking=True,
    )
    await hass.services.async_call(
        "humidifier", "set_mode", {"entity_id": entity.entity_id, "mode": "auto"}, blocking=True
    )
    await hass.async_block_till_done()
    assert calls == ["Auto", 55]
    assert hass.states.get(entity.entity_id).attributes["mode"] == "auto"
