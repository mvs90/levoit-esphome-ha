"""Template recognition, value reading and rendering, on a real builder file."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

import pytest

from custom_components.levoit_esphome.templates import (
    MARKER_PREFIX,
    ConfigValues,
    CustomEsp,
    Template,
    TemplateError,
    Value,
    builder_esp,
    config_values,
    new_api_key,
    normalize_pin,
    ota_encryption_from_password,
    ota_password_from_encryption,
    parse_templates,
    render,
    render_custom,
    secret_key,
    suggest_name,
    supports_ota_encryption,
    template_of,
    valid_board,
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
    # the repo notes give way to a header that says how to make it your own
    assert "make-builder-yaml" not in text
    assert "# Generated from" not in text
    assert "DELETE THE FIRST LINE" in text
    assert "https://github.com/tuct/levoit/tree/main/devices/levoit-everest-air" in text
    # everything below the header untouched
    body = BUILDER[BUILDER.index("substitutions:") :]
    assert text[text.index("substitutions:") :].count("\n") == body.count("\n")
    assert template_of(text, TEMPLATES) == EVEREST_C3


def test_render_custom() -> None:
    """Own board and pins on the builder file; no marker, so it is never rewritten."""
    assert builder_esp(BUILDER) == CustomEsp(
        board="seeed_xiao_esp32c3", rx_pin="GPIO05", tx_pin="GPIO06"
    )
    esp = CustomEsp(board="seeed_xiao_esp32s3", rx_pin="GPIO5", tx_pin="GPIO4")
    text = render_custom(BUILDER, EVEREST_C3, VALUES, esp)
    assert template_of(text, TEMPLATES) is None  # custom
    assert MARKER_PREFIX not in text
    assert "# Generated from" not in text
    assert text.startswith(f"# Made by Levoit ESPHome from {EVEREST_C3.file}")
    assert "esp32:\n  board: seeed_xiao_esp32s3\n  framework:\n    type: esp-idf\n\n" in text
    assert "seeed_xiao_esp32c3" not in text
    assert "  rx_pin: GPIO5\n" in text
    assert "  tx_pin: GPIO4\n" in text
    assert config_values(text) == VALUES  # name, secrets, channel as for a template


def test_pins_and_boards() -> None:
    """Pins are normalised to GPIOn; board names follow ESPHome's."""
    pins = [normalize_pin(p) for p in ("GPIO05", "5", "gpio21", "IO5", "GPIO123", "")]
    assert pins == ["GPIO5", "GPIO5", "GPIO21", None, None, None]
    assert valid_board("seeed_xiao_esp32s3")
    assert valid_board("esp32-c6-devkitc-1")
    assert not valid_board("My Board")
    assert not valid_board("")


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


def test_parse_templates_skips_unknown_variants() -> None:
    """A variant this version does not know (a future ESP) is not offered."""
    entry = {
        "title": "Levoit Core 300S",
        "model": "CORE300S",
        "board": "esp32-s3-devkitc-1",
        "name": "levoit-core300s-s3",
        "file": "devices/levoit-core300s/levoit-core300s-builder-s3.yaml",
        "source": "devices/levoit-core300s/levoit-core300s-s3.yaml",
    }
    data = {
        "version": 1,
        "templates": [{**entry, "variant": "s3"}, {**entry, "variant": "c6"}],
    }
    assert [t.variant for t in parse_templates(data)] == ["s3"]


@pytest.mark.parametrize("key", [Value(secret="device_ota_key"), Value(inline="A" * 43 + "=")])
def test_encrypted_ota_survives_template_refresh(key: Value) -> None:
    """Refreshing a marked template must not downgrade encrypted OTA to open OTA."""
    values = ConfigValues(
        name="secure-air", api_key=VALUES.api_key, ota_encryption_key=key, channel="stable"
    )
    text = render(BUILDER, EVEREST_C3, values)
    assert "    encryption:\n      key: " + key.yaml in text
    assert "ota_password" not in text
    assert config_values(text) == values
    assert render(BUILDER, EVEREST_C3, config_values(text)) == text


@pytest.mark.parametrize("ota", ["encryption:", "encryption: {}"])
def test_ota_inheriting_api_key_survives_refresh(ota: str) -> None:
    original = BUILDER.replace("password: !secret ota_password", ota)
    values = config_values(original)
    expected = ConfigValues(
        name=values.name, api_key=values.api_key, channel="stable", ota_uses_api_key=True
    )
    assert values == expected
    refreshed = render(BUILDER, EVEREST_C3, values)
    assert "  - platform: esphome\n    encryption:\n" in refreshed
    assert config_values(refreshed) == expected
    assert "ota_password" not in refreshed


def test_unrecognised_ota_encryption_fails_closed() -> None:
    """A format we cannot preserve must fail before the config is written."""
    text = render(BUILDER, EVEREST_C3, ConfigValues(name="secure-air"))
    text = text.replace(
        "  - platform: esphome",
        "  - platform: esphome\n    encryption:\n"
        "      key: !secret ota_key\n      allow_plaintext: true",
    )
    with pytest.raises(TemplateError, match="unsupported OTA encryption"):
        config_values(text)


def test_mixed_encrypted_ota_platforms_fail_closed() -> None:
    text = render(
        BUILDER,
        EVEREST_C3,
        ConfigValues(name="secure-air", ota_encryption_key=Value(secret="ota_key")),
    )
    text = text.replace("ota:\n", "ota:\n  - platform: http_request\n")
    with pytest.raises(TemplateError, match="unsupported encrypted OTA"):
        config_values(text)


def test_inline_encrypted_ota_and_yaml_comments() -> None:
    text = render(BUILDER, EVEREST_C3, ConfigValues(name="secure-air"))
    text = text.replace(
        "ota:\n  - platform: esphome\n",
        '"ota": [{platform: esphome, encryption: {key: !secret device_ota_key}}] # keep secure\n',
    )
    values = config_values(text)
    assert values.ota_encryption_key == Value(secret="device_ota_key")
    assert "    encryption:\n      key: !secret device_ota_key" in render(
        BUILDER, EVEREST_C3, values
    )


@pytest.mark.parametrize(
    "ota",
    [
        "ota: !include private-ota.yaml",
        "ota: []",
        "ota: [{platform: esphome, encryption: {}}]",
        "ota:\n  - platform: esphome\n    encryption: !include private-ota.yaml",
        "ota: [{platform: esphome, encryption: {key: !secret ota_key, "
        "old_key: !secret old_ota_key}}]",
        "ota: [{platform: esphome, encryption: {key: !secret ota_key, "
        "allow_plaintext_upload: true}}]",
        "ota: [{platform: esphome, password: !secret ota_password, "
        "encryption: {key: !secret ota_key}}]",
        "ota: [{platform: esphome, encryption: {key: !secret ota_key, key: other}}]",
        'ota: [{platform: esphome, encryption: {key: "${private_key}"}}]',
        "ota: [{platform: esphome}]\npackages: !include private.yaml",
        "ota: [{platform: esphome}]\nota: [{platform: esphome}]",
    ],
)
def test_refuses_ota_that_cannot_be_preserved(ota: str) -> None:
    text = render(BUILDER, EVEREST_C3, ConfigValues(name="secure-air"))
    with pytest.raises(TemplateError, match="custom config"):
        config_values(text.replace("ota:\n  - platform: esphome\n", ota + "\n"))


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("ref: stable", "ref: 1.7.3"),
        ("https://github.com/tuct/levoit", "https://github.com/owner/levoit"),
    ],
)
def test_refresh_refuses_to_rewrite_pinned_or_forked_source(before: str, after: str) -> None:
    with pytest.raises(TemplateError, match="custom config"):
        config_values(BUILDER.replace(before, after))


def test_refresh_does_not_enable_a_native_api_that_was_removed() -> None:
    text = render(
        BUILDER,
        EVEREST_C3,
        ConfigValues(name="secure-air", ota_encryption_key=Value(secret="ota_key")),
    )
    without_api = text.replace("\napi:\n", "\n", 1)
    assert without_api != text
    with pytest.raises(TemplateError, match="without the native API"):
        config_values(without_api)


def test_supports_ota_encryption() -> None:
    """ESPHome 2026.9.0 brought it; an unknown version counts as new enough."""
    assert supports_ota_encryption("2026.9.0")
    assert supports_ota_encryption("2026.11.0")
    assert supports_ota_encryption("2027.1.0b1")
    assert not supports_ota_encryption("2026.8.2")
    assert not supports_ota_encryption("2025.12.0")
    assert supports_ota_encryption(None)
    assert supports_ota_encryption("dev")


def test_ota_password_and_encryption_swap() -> None:
    """The OTA line swapped each way, text only; a config without the line is refused."""
    with_password = render(BUILDER, EVEREST_C3, VALUES)
    encrypted = ota_encryption_from_password(with_password)
    assert encrypted == with_password.replace(
        "    password: !secret bedroom_air_ota_password\n", "    encryption:\n"
    )
    assert config_values(encrypted) == replace(VALUES, ota_password=None, ota_uses_api_key=True)
    assert ota_password_from_encryption(encrypted, "bedroom_air_ota_password") == with_password
    with pytest.raises(TemplateError, match="ota password line"):
        ota_encryption_from_password(encrypted)
    with pytest.raises(TemplateError, match="ota encryption"):
        ota_password_from_encryption(with_password, "x")
    # an explicit key is not inherited encryption: left alone
    explicit = render(
        BUILDER,
        EVEREST_C3,
        replace(VALUES, ota_password=None, ota_encryption_key=Value(secret="k")),
    )
    with pytest.raises(TemplateError, match="ota encryption"):
        ota_password_from_encryption(explicit, "x")
