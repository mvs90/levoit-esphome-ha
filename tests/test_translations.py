"""Check that Home Assistant can load the German integration translations."""

import json
from pathlib import Path
import re

from custom_components.levoit_esphome.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

TRANSLATIONS = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN / "translations"


def test_german_translation_keys_and_placeholders_match_english() -> None:
    """Provide the same keys and interpolation fields as the source catalog."""

    def keys(node: dict, prefix: str = "") -> dict[str, set[str]]:
        fields = {}
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                fields.update(keys(value, path))
            else:
                assert isinstance(value, str) and value.strip(), path
                fields[path] = set(re.findall(r"\{[\w]+\}", value))
        return fields

    en, de = (json.loads((TRANSLATIONS / f"{lang}.json").read_text()) for lang in ("en", "de"))
    assert keys(de) == keys(en)


async def test_home_assistant_loads_german_translation(hass: HomeAssistant) -> None:
    """Use Home Assistant's translation loader for options and entity names."""
    options = await async_get_translations(hass, "de", "options", [DOMAIN])
    entities = await async_get_translations(hass, "de", "entity", [DOMAIN])
    assert options[f"component.{DOMAIN}.options.step.init.data.show_panel"] == (
        "In der Seitenleiste anzeigen"
    )
    assert entities[f"component.{DOMAIN}.entity.button.compile.name"] == "Firmware kompilieren"
