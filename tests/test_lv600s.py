"""LV600S discovery and mapping must work without pretending it is a fan."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.levoit_esphome.controls import config_names, match_controls, page_supported
from custom_components.levoit_esphome.versions import component_model, component_source
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
        },
    )
    device_id = er.async_get(hass).async_get(ids["switch.power"]).device_id
    found = match_controls(hass, device_id, "LV600S")
    assert found["switch.power"] == ids["switch.power"]
    assert found["number.humidity_target"] == ids["number.target"]
    assert found["number.warm_level"] == ids["number.warm"]
    assert found["number.timer"] == ids["number.timer"]
    assert "fan.fan" not in found
