"""Template recognition, value reading and rendering, on a real builder file."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from custom_components.levoit_esphome.templates import (
    MARKER_PREFIX,
    ConfigValues,
    Template,
    TemplateError,
    Value,
    config_values,
    new_api_key,
    render,
    secret_key,
    suggest_name,
    template_of,
    valid_name,
    with_channel,
)

BUILDER = (Path(__file__).parent / "fixtures" / "levoit-everest-air-builder-c3.yaml").read_text(
    encoding="utf-8"
)
EVEREST_C3 = Template(
    title="Levoit Everest Air",
    model="EVERESTAIR",
    variant="xiao_c3",
    board="seeed_xiao_esp32c3",
    name="levoit-everest-air-c3",
    file="devices/levoit-everest-air/levoit-everest-air-builder-c3.yaml",
    source="devices/levoit-everest-air/levoit-everest-air-c3.yaml",
)
OTHER = Template(
    title="Levoit Core 300S",
    model="CORE300S",
    variant="original",
    board="esp32dev",
    name="levoit-core300s",
    file="devices/levoit-core300s/levoit-core300s-builder.yaml",
    source="devices/levoit-core300s/levoit-core300s.yaml",
)
TEMPLATES = [OTHER, EVEREST_C3]

VALUES = ConfigValues(
    name="bedroom-air",
    api_key=Value(secret="bedroom_air_api_key"),
    ota_password=Value(secret="bedroom_air_ota_password"),
    channel="main",
)


def test_pasted_builder_file_is_recognised() -> None:
    """A builder file pasted by hand: by its "Generated from" header."""
    assert template_of(BUILDER, TEMPLATES) == EVEREST_C3


def test_custom_config() -> None:
    """No marker, no generated header: custom."""
    assert template_of("esphome:\n  name: my-own\n", TEMPLATES) is None


def test_render() -> None:
    """Name, secrets and channel are the device's; the rest is the template."""
    text = render(BUILDER, EVEREST_C3, VALUES)
    assert text.startswith(f"{MARKER_PREFIX}{EVEREST_C3.file}\n")
    assert "  device_name: bedroom-air\n" in text
    assert "    key: !secret bedroom_air_api_key\n" in text
    assert "    password: !secret bedroom_air_ota_password\n" in text
    assert "      ref: main\n" in text
    assert "!secret api_key" not in text
    assert "!secret ota_password" not in text
    # Wi-Fi stays on the shared secrets
    assert "!secret wifi_ssid" in text
    assert "!secret wifi_password" in text
    # everything else untouched
    assert text.count("\n") == BUILDER.count("\n") + 1
    assert template_of(text, TEMPLATES) == EVEREST_C3


def test_render_round_trip() -> None:
    """Values read back from a rendered config are the ones put in."""
    text = render(BUILDER, EVEREST_C3, VALUES)
    assert config_values(text) == VALUES
    # rendering again (template refresh) changes nothing, one marker only
    again = render(BUILDER, EVEREST_C3, config_values(text))
    assert again == text
    assert len(re.findall(re.escape(MARKER_PREFIX), again)) == 1


def test_render_without_keys() -> None:
    """A device without API encryption or OTA password keeps it that way."""
    text = render(BUILDER, EVEREST_C3, ConfigValues(name="bedroom-air"))
    assert "encryption:" not in text
    assert "    key:" not in text
    assert "password: !secret ota_password" not in text
    assert "      ref: stable\n" in text  # channel left as in the template
    assert config_values(text) == ConfigValues(name="bedroom-air", channel="stable")


def test_render_inline_values() -> None:
    """Inline values stay inline (quoted)."""
    values = ConfigValues(
        name="bedroom-air",
        api_key=Value(inline="abc+/="),
        ota_password=Value(inline='pa"ss'),
    )
    text = render(BUILDER, EVEREST_C3, values)
    assert '    key: "abc+/="\n' in text
    assert config_values(text).api_key == Value(inline="abc+/=")


def test_render_rejects_unknown_shape() -> None:
    """A file without the expected lines is refused, not half-rendered."""
    with pytest.raises(TemplateError):
        render("esphome:\n  name: x\n", EVEREST_C3, VALUES)


def test_with_channel() -> None:
    """Only the component ref changes; unknown channels are refused."""
    text = render(BUILDER, EVEREST_C3, VALUES)
    stable = with_channel(text, "stable")
    assert stable == text.replace("      ref: main\n", "      ref: stable\n")
    assert with_channel(stable, "stable") == stable
    with pytest.raises(TemplateError):
        with_channel(text, "my-branch")
    with pytest.raises(TemplateError):
        with_channel("esphome:\n  name: x\n", "main")


def test_config_values_of_pasted_builder_file() -> None:
    """A pasted builder file: shared secrets, stable."""
    assert config_values(BUILDER) == ConfigValues(
        name="levoit-everest-air-c3",
        api_key=Value(secret="api_key"),
        ota_password=Value(secret="ota_password"),
        channel="stable",
    )


def test_names_and_keys() -> None:
    """Name rules, suggestions and secret names."""
    assert valid_name("levoit-everest-air-c3")
    assert not valid_name("Levoit Everest")
    assert not valid_name("-x")
    assert not valid_name("a" * 32)
    assert suggest_name("levoit-everest-air-c3", set()) == "levoit-everest-air-c3"
    assert (
        suggest_name("levoit-everest-air-c3", {"levoit-everest-air-c3", "levoit-everest-air-c3-2"})
        == "levoit-everest-air-c3-3"
    )
    assert secret_key("levoit-everest-air-c3", "api_key") == "levoit_everest_air_c3_api_key"
    key = new_api_key()
    assert len(key) == 44 and key.endswith("=")
