"""Fixtures: a stub Device Builder and stub GitHub heads.

The esphome integration is marked as loaded instead of set up: its setup needs
Bluetooth, ffmpeg and more, none of which matter here. All access to it goes
through device_builder.py, which these fixtures replace.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.levoit_esphome.versions import ChannelHead
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

MAC = "aa:bb:cc:dd:ee:ff"
OTHER_MAC = "11:22:33:44:55:66"

HEADS = {
    "stable": ChannelHead(
        release="1.8.0",
        commit="abcdef1",
        notes="## 1.8.0\n\nRelease notes",
        url="https://github.com/tuct/levoit/releases/tag/1.8.0",
    ),
    "main": ChannelHead(
        release="1.8.0",
        commit="1234567",
        url="https://github.com/tuct/levoit/commits/main",
    ),
}

PURIFIER_CONFIG = {
    "esphome": {"name": "bedroom-purifier"},
    "levoit": {"model": "CORE300S", "id": "levoit_1"},
    "external_components": [
        {
            "source": {"type": "git", "url": "https://github.com/tuct/levoit", "ref": "stable"},
            "components": ["levoit"],
        }
    ],
    # resolved secrets come along in json-config; the integration must not keep them
    "api": {"encryption": {"key": "c2VjcmV0LWtleS1kby1ub3Qta2VlcA=="}},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@dataclass
class FakeApi:
    """Stands in for esphome_dashboard_api.ESPHomeDashboardAPI."""

    configured: list[dict[str, Any]] = field(default_factory=list)
    configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    compile: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))
    upload: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))
    get_config_calls: list[str] = field(default_factory=list)

    async def get_devices(self) -> dict[str, Any]:
        return {"configured": self.configured, "importable": []}

    async def get_config(self, configuration: str) -> dict[str, Any] | None:
        self.get_config_calls.append(configuration)
        return self.configs.get(configuration)


@dataclass
class FakeBuilder:
    """Stands in for the esphome integration's dashboard coordinator."""

    api: FakeApi
    supports_build_queue: bool = True


@pytest.fixture
def builder() -> FakeBuilder:
    """A Device Builder with the bedroom purifier's config."""
    return FakeBuilder(
        api=FakeApi(
            configured=[
                {
                    "name": "bedroom-purifier",
                    "configuration": "bedroom-purifier.yaml",
                    "deployed_version": "2026.11.0",
                    "current_version": "2026.11.0",
                    "loaded_integrations": ["api", "levoit", "uart", "wifi"],
                },
                {
                    "name": "garage-sensor",
                    "configuration": "garage-sensor.yaml",
                    "deployed_version": "2026.11.0",
                    "current_version": "2026.11.0",
                    "loaded_integrations": ["api", "dht", "wifi"],
                },
            ],
            configs={"bedroom-purifier.yaml": PURIFIER_CONFIG},
        )
    )


@pytest.fixture
def patch_sources(builder: FakeBuilder) -> Generator[AsyncMock]:
    """Use the fake Device Builder and fixed GitHub heads."""
    heads = AsyncMock(return_value=HEADS)
    with (
        patch(
            "custom_components.levoit_esphome.coordinator.async_get_device_builder",
            return_value=builder,
        ),
        patch(
            "custom_components.levoit_esphome.config_flow.async_get_device_builder",
            return_value=builder,
        ),
        patch("custom_components.levoit_esphome.coordinator.async_fetch_heads", heads),
    ):
        yield heads


def add_esphome_device(
    hass: HomeAssistant, name: str, mac: str, title: str, version: str | None
) -> str | None:
    """Register an ESPHome device like the esphome integration does.

    Returns the entity_id of its version sensor, if it has one.
    """
    entry = MockConfigEntry(domain="esphome", data={"device_name": name, "host": f"{name}.local"})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name=title,
    )
    if version is None:
        return None
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        "esphome",
        f"{mac}-text_sensor-esp_version",
        device_id=device.id,
        config_entry=entry,
        suggested_object_id=f"{name}_esp_version",
    )
    hass.states.async_set(entity.entity_id, version)
    return entity.entity_id


@pytest.fixture
def esphome_devices(hass: HomeAssistant) -> dict[str, str | None]:
    """The purifier (ours, on 1.7.0) and an unrelated ESPHome device."""
    hass.config.components.add("esphome")
    return {
        "purifier": add_esphome_device(
            hass, "bedroom-purifier", MAC, "Bedroom purifier", "1.7.0+10361cc esphome"
        ),
        "other": add_esphome_device(hass, "garage-sensor", OTHER_MAC, "Garage sensor", None),
    }
