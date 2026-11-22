"""Version parsing and comparison."""

from __future__ import annotations

import pytest

from custom_components.levoit_esphome.versions import (
    ChannelHead,
    Reported,
    component_model,
    component_source,
    is_behind,
    parse_reported,
)

HEAD = ChannelHead(release="1.8.0", commit="abcdef1")
OURS = "https://github.com/tuct/levoit"
FORK = "https://github.com/someone/levoit"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("1.7.0 esphome", Reported("1.7.0")),
        ("1.7.0+3fa21c4 esphome", Reported("1.7.0", "3fa21c4")),
        ("1.7.0+3fa21c4.dirty esphome", Reported("1.7.0", "3fa21c4", dirty=True)),
        ("1.7.0+3fa21c4bb esphome", Reported("1.7.0", "3fa21c4")),
        ("1.0.2", None),  # MCU version: no " esphome"
        ("1.7.0+3fa21c4", None),
        ("1.8.0-beta.1+3fa21c4 esphome", Reported("1.8.0-beta.1", "3fa21c4")),
        ("unknown", None),
        ("", None),
        (None, None),
        ("22.5", None),
        ("on", None),
    ],
)
def test_parse_reported(state: str | None, expected: Reported | None) -> None:
    """Only the esp_version format parses."""
    assert parse_reported(state) == expected


def test_text() -> None:
    """Versions as shown in Home Assistant."""
    assert Reported("1.7.0").text == "1.7.0"
    assert Reported("1.7.0", "3fa21c4").text == "1.7.0+3fa21c4"
    assert Reported("1.7.0", "3fa21c4", dirty=True).text == "1.7.0+3fa21c4.dirty"
    assert HEAD.text == "1.8.0+abcdef1"


@pytest.mark.parametrize(
    ("reported", "channel", "behind"),
    [
        # main: commits decide where both have one
        (Reported("1.8.0", "abcdef1"), "main", False),  # at the head
        (Reported("1.7.0", "10361cc"), "main", True),  # older commit
        (Reported("1.8.0", "0000000"), "main", True),  # other commit, same release
        (Reported("1.7.0"), "main", True),  # no commit: release number decides
        (Reported("1.8.0"), "main", False),
        # stable: only a newer release counts
        (Reported("1.8.0", "abcdef1"), "stable", False),
        (Reported("1.8.0", "0000000"), "stable", False),  # main build after 1.8.0
        (Reported("1.7.0", "10361cc"), "stable", True),
        (Reported("1.7.0"), "stable", True),
        (Reported("1.9.0", "0000000"), "stable", False),
        # never a local build
        (Reported("1.7.0", "10361cc", dirty=True), "main", False),
        (Reported("1.7.0", "10361cc", dirty=True), "stable", False),
    ],
)
def test_is_behind(reported: Reported, channel: str, behind: bool) -> None:
    """main compares commits, stable compares releases."""
    assert is_behind(reported, HEAD, channel) is behind


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ({"type": "git", "url": OURS, "ref": "stable"}, ("stable", "stable")),
        ({"type": "git", "url": f"{OURS}.git", "ref": "main"}, ("main", "main")),
        ({"type": "git", "url": OURS}, ("main", None)),
        ({"type": "git", "url": OURS, "ref": "1.7.0"}, ("pinned", "1.7.0")),
        ({"type": "git", "url": FORK, "ref": "stable"}, ("pinned", "stable")),
        ({"type": "local", "path": "../../components"}, ("local", None)),
        ("github://tuct/levoit@stable", ("stable", "stable")),
        ("github://tuct/levoit", ("main", None)),
    ],
)
def test_component_source(source: object, expected: tuple[str, str | None]) -> None:
    """Channel from the component's source."""
    config = {"external_components": [{"source": source, "components": ["levoit"]}]}
    assert component_source(config) == expected


def test_component_source_skips_other_components() -> None:
    """An external_components entry for something else is not ours."""
    config = {
        "external_components": [
            {"source": {"type": "local", "path": "x"}, "components": ["levoit_audio"]},
            {"source": {"type": "git", "url": OURS, "ref": "stable"}, "components": ["levoit"]},
        ]
    }
    assert component_source(config) == ("stable", "stable")
    assert component_source({}) is None


def test_component_model() -> None:
    """model: of the levoit or philips block."""
    assert component_model({"levoit": {"model": "CORE300S"}}) == "CORE300S"
    assert component_model({"philips": {"model": "AC0951"}}) == "AC0951"
    assert component_model({"levoit": [{"model": "VITAL200S"}]}) == "VITAL200S"
    assert component_model({"fan": {}}) is None
