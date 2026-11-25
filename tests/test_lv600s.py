"""LV600S discovery and mapping must work without pretending it is a fan."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.levoit_esphome.controls import config_names, page_supported
from custom_components.levoit_esphome.versions import component_model, component_source
from homeassistant.core import HomeAssistant

from .conftest import MAC, add_esphome_device
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
