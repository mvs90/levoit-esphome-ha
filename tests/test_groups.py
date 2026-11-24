"""Purifier groups in Home Assistant: the loop, entities and panel commands."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.levoit_esphome.const import DOMAIN
from custom_components.levoit_esphome.groups import STORAGE_KEY
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from .conftest import MAC, add_esphome_device

LIVING_MAC = "de:ad:be:ef:00:03"
UNIT = {"unit_of_measurement": "µg/m³"}
PRESETS = ["Manual", "Sleep", "Auto"]
LEVEL = "sensor.living_room_level"
CONTROL = "switch.living_room_control"
ACTIVE = "binary_sensor.living_room_active"
GROUP_FAN = "fan.living_room"
AIR_QUALITY = "sensor.living_room_air_quality"
MEMBERS = ["fan.bedroom", "fan.living"]

type Calls = list[tuple[str, str, dict[str, Any]]]


def _add_entities(hass: HomeAssistant, mac: str, entities: dict[str, str]) -> None:
    """ESPHome entities ('domain.object_id' -> name) on the device with that MAC."""
    dev_reg = dr.async_get(hass)
    entry, device = next(
        (entry, device)
        for entry in hass.config_entries.async_entries("esphome")
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if (dr.CONNECTION_NETWORK_MAC, mac) in device.connections
    )
    for key, name in entities.items():
        domain, object_id = key.split(".", 1)
        er.async_get(hass).async_get_or_create(
            domain,
            "esphome",
            f"{mac}-{domain}-{object_id}",
            device_id=device.id,
            config_entry=entry,
            original_name=name,
            suggested_object_id=object_id,
        )


def _purifiers(hass: HomeAssistant) -> None:
    """Two purifiers with a fan and a PM2.5 sensor each.

    Bedroom: 4 speeds, on in Auto. Living: 3 speeds, off.
    """
    hass.config.components.add("esphome")
    add_esphome_device(hass, "bedroom-purifier", MAC, "Bedroom purifier", "1.7.0+10361cc esphome")
    add_esphome_device(
        hass,
        "living-purifier",
        LIVING_MAC,
        "Living purifier",
        "1.7.0+10361cc esphome",
        model="CORE300S",
    )
    _add_entities(hass, MAC, {"fan.bedroom": "Fan", "sensor.bedroom_pm25": "PM 2.5"})
    _add_entities(hass, LIVING_MAC, {"fan.living": "Fan", "sensor.living_pm25": "PM 2.5"})
    hass.states.async_set(
        "fan.bedroom",
        "on",
        {"preset_mode": "Auto", "preset_modes": PRESETS, "percentage": 25, "percentage_step": 25},
    )
    hass.states.async_set(
        "fan.living",
        "off",
        {
            "preset_mode": None,
            "preset_modes": PRESETS,
            "percentage": 0,
            "percentage_step": 100 / 3,
        },
    )
    hass.states.async_set("sensor.bedroom_pm25", "5", UNIT)
    hass.states.async_set("sensor.living_pm25", "5", UNIT)


async def _fake_fans(hass: HomeAssistant) -> Calls:
    """Fan services that act like the purifiers: the state follows, with the call's context.

    The fan integration is set up first, so its services (registered once)
    do not replace these when the integration's group fans load.
    """
    assert await async_setup_component(hass, "fan", {})
    calls: Calls = []

    async def handle(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        calls.append(
            (call.service, entity_id, {k: v for k, v in call.data.items() if k != "entity_id"})
        )
        state = hass.states.get(entity_id)
        attributes = dict(state.attributes)
        value = state.state
        if call.service == "turn_off":
            value = "off"
        elif call.service == "turn_on":
            value = "on"
            if "percentage" in call.data:
                attributes["percentage"] = call.data["percentage"]
                attributes["preset_mode"] = "Manual"
        elif call.service == "set_preset_mode":
            value = "on"
            attributes["preset_mode"] = call.data["preset_mode"]
        hass.states.async_set(entity_id, value, attributes, context=call.context)

    for service in ("turn_on", "turn_off", "set_preset_mode"):
        hass.services.async_register("fan", service, handle)
    return calls


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Levoit ESPHome", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def _call(client: Any, message: dict[str, Any]) -> dict[str, Any]:
    """Send a command; its result, skipping subscription events."""
    await client.send_json_auto_id(message)
    while True:
        msg = await client.receive_json()
        if msg["id"] == message["id"] and msg["type"] == "result":
            return msg


async def _save(client: Any, **group: Any) -> dict[str, Any]:
    msg = await _call(
        client,
        {"type": "levoit_esphome/groups/save", "group": {"name": "Living room", **group}},
    )
    assert msg["success"], msg
    return msg["result"]


async def _settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def _later(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await _settle(hass)


def _pm(hass: HomeAssistant, value: float, sensor: str = "sensor.living_pm25") -> None:
    hass.states.async_set(sensor, str(value), UNIT)


@pytest.mark.usefixtures("patch_sources")
async def test_group_takes_over_and_hands_back(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Bad air: all members in Manual at their speed; clean air: one level per hold, then back."""
    calls = await _fake_fans(hass)
    _purifiers(hass)
    await _setup(hass)
    client = await hass_ws_client(hass)

    group = await _save(client, members=MEMBERS)
    assert [(s["entity_id"], s["type"], s["source"]) for s in group["sensors"]] == [
        ("sensor.bedroom_pm25", "pm25", "auto"),
        ("sensor.living_pm25", "pm25", "auto"),
    ]
    assert hass_storage[STORAGE_KEY]["data"]["groups"][0]["name"] == "Living room"
    await _settle(hass)
    assert calls == []
    assert hass.states.get(CONTROL).state == "on"
    assert hass.states.get(LEVEL).state == "0"
    assert hass.states.get(LEVEL).attributes["status"] == "watching"
    assert hass.states.get(ACTIVE).state == "off"

    _pm(hass, 783)
    await _settle(hass)
    # 4 speeds: 4; 3 speeds: its top speed 3
    assert calls == [
        ("turn_on", "fan.bedroom", {"percentage": 100}),
        ("turn_on", "fan.living", {"percentage": 100}),
    ]
    level = hass.states.get(LEVEL)
    assert level.state == "4"
    assert level.attributes["status"] == "in_control"
    assert level.attributes["reason"].startswith("PM2.5 783 µg/m³")
    assert level.attributes["worst_sensor"] == "sensor.living_pm25"
    assert level.attributes["members_in_control"] == MEMBERS
    assert hass.states.get(ACTIVE).state == "on"

    calls.clear()
    _pm(hass, 3)
    await _settle(hass)
    assert hass.states.get(LEVEL).state == "4"  # holds
    assert calls == []

    await _later(hass, freezer, 10)
    assert hass.states.get(LEVEL).state == "3"
    assert calls == [
        ("turn_on", "fan.bedroom", {"percentage": 75}),
        ("turn_on", "fan.living", {"percentage": 66}),
    ]
    calls.clear()
    await _later(hass, freezer, 10)
    assert hass.states.get(LEVEL).state == "2"
    assert calls == [("turn_on", "fan.bedroom", {"percentage": 50})]  # living stays on 2
    await _later(hass, freezer, 10)
    assert hass.states.get(LEVEL).state == "1"
    calls.clear()

    await _later(hass, freezer, 10)
    assert hass.states.get(LEVEL).state == "0"
    # back as they were: bedroom in Auto, living off
    assert calls == [
        ("set_preset_mode", "fan.bedroom", {"preset_mode": "Auto"}),
        ("turn_off", "fan.living", {}),
    ]
    assert hass.states.get(ACTIVE).state == "off"


@pytest.mark.usefixtures("patch_sources")
async def test_manual_change_pauses_that_member(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A person's change pauses the group for that purifier only, for manual_pause_min."""
    calls = await _fake_fans(hass)
    _purifiers(hass)
    await _setup(hass)
    client = await hass_ws_client(hass)
    await _save(client, members=MEMBERS)
    _pm(hass, 783)
    await _settle(hass)
    calls.clear()

    bedroom = hass.states.get("fan.bedroom")
    hass.states.async_set(
        "fan.bedroom", "on", {**bedroom.attributes, "percentage": 25}, context=Context()
    )
    await _settle(hass)
    assert calls == []  # not set back
    assert hass.states.get(LEVEL).attributes["members_in_control"] == ["fan.living"]

    _pm(hass, 60)  # level 3, after the hold
    await _later(hass, freezer, 10)
    assert hass.states.get(LEVEL).state == "3"
    assert calls == [("turn_on", "fan.living", {"percentage": 66})]
    calls.clear()

    await _later(hass, freezer, 25)  # 35 minutes after the change: pause over
    assert calls == [("turn_on", "fan.bedroom", {"percentage": 75})]
    assert hass.states.get(LEVEL).attributes["members_in_control"] == MEMBERS


@pytest.mark.usefixtures("patch_sources")
async def test_control_switch_and_manual_mode(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """The switch hands back and pauses; Manual mode runs one level, sensors ignored."""
    calls = await _fake_fans(hass)
    _purifiers(hass)
    await _setup(hass)
    client = await hass_ws_client(hass)
    group = await _save(client, members=MEMBERS)
    _pm(hass, 783)
    await _settle(hass)
    calls.clear()

    await hass.services.async_call("switch", "turn_off", {"entity_id": CONTROL}, blocking=True)
    await _settle(hass)
    assert hass.states.get(CONTROL).state == "off"
    assert hass.states.get(LEVEL).attributes["status"] == "paused"
    assert calls == [
        ("set_preset_mode", "fan.bedroom", {"preset_mode": "Auto"}),
        ("turn_off", "fan.living", {}),
    ]
    calls.clear()

    await hass.services.async_call("switch", "turn_on", {"entity_id": CONTROL}, blocking=True)
    await _settle(hass)
    assert hass.states.get(LEVEL).state == "4"
    calls.clear()

    await _save(client, id=group["id"], members=MEMBERS, mode="manual", manual_level=2)
    await _settle(hass)
    assert hass.states.get(LEVEL).state == "2"
    assert hass.states.get(LEVEL).attributes["status"] == "manual"
    assert calls == [
        ("turn_on", "fan.bedroom", {"percentage": 50}),
        ("turn_on", "fan.living", {"percentage": 66}),
    ]


@pytest.mark.usefixtures("patch_sources")
async def test_panel_commands(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    """Subscribe, validation, preview, dismiss and delete."""
    calls = await _fake_fans(hass)
    _purifiers(hass)
    entry = await _setup(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "levoit_esphome/groups/subscribe"})
    assert (await client.receive_json())["success"]
    event = (await client.receive_json())["event"]
    assert event["groups"] == []
    assert [(p["entity_id"], p["speeds"], p["group_id"]) for p in event["purifiers"]] == [
        ("fan.bedroom", 4, None),
        ("fan.living", 3, None),
    ]
    assert event["purifiers"][0]["sensors"] == [
        {"entity_id": "sensor.bedroom_pm25", "type": "pm25"}
    ]

    msg = await _call(
        client,
        {"type": "levoit_esphome/groups/save", "group": {"name": "x", "members": ["fan.bedroom"]}},
    )
    assert msg["error"]["code"] == "members"
    msg = await _call(
        client,
        {
            "type": "levoit_esphome/groups/save",
            "group": {"name": "x", "members": ["fan.bedroom", "fan.unknown"]},
        },
    )
    assert msg["error"]["code"] == "members"

    _pm(hass, 40)
    msg = await _call(
        client,
        {
            "type": "levoit_esphome/groups/preview",
            "group": {"members": MEMBERS, "removed_sensors": ["sensor.bedroom_pm25"]},
        },
    )
    assert msg["success"], msg
    preview = msg["result"]
    assert preview["level"] == 2
    assert preview["worst"] == "sensor.living_pm25"
    assert preview["sensors"] == [
        {
            "entity_id": "sensor.living_pm25",
            "type": "pm25",
            "source": "auto",
            "value": 40.0,
            "level": 2,
        }
    ]
    assert preview["members"] == [
        {"entity_id": "fan.bedroom", "speeds": 4, "speed": 2},
        {"entity_id": "fan.living", "speeds": 3, "speed": 2},
    ]
    assert calls == []  # a preview changes nothing

    group = await _save(client, members=MEMBERS, removed_sensors=["sensor.bedroom_pm25"])
    assert [s["entity_id"] for s in group["sensors"]] == ["sensor.living_pm25"]
    msg = await _call(
        client,
        {"type": "levoit_esphome/groups/save", "group": {"name": "Other", "members": MEMBERS}},
    )
    assert msg["error"]["code"] == "members"  # already in Living room

    assert (await _call(client, {"type": "levoit_esphome/groups/dismiss", "area_id": "hall"}))[
        "success"
    ]
    await _settle(hass)
    msg = await _call(client, {"type": "levoit_esphome/groups/list"})
    assert msg["result"]["dismissed_areas"] == ["hall"]
    (listed,) = msg["result"]["groups"]
    assert listed["state"]["level"] == 2
    assert {p["entity_id"]: p["group_id"] for p in msg["result"]["purifiers"]} == {
        "fan.bedroom": group["id"],
        "fan.living": group["id"],
    }
    assert hass.states.get(LEVEL).state == "2"
    calls.clear()

    msg = await _call(client, {"type": "levoit_esphome/groups/delete", "group_id": group["id"]})
    assert msg["success"], msg
    await _settle(hass)
    assert ("set_preset_mode", "fan.bedroom", {"preset_mode": "Auto"}) in calls
    assert hass.states.get(LEVEL) is None
    assert (
        dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, f"group_{group['id']}"), entry.entry_id
        )
        is None
    )
    msg = await _call(client, {"type": "levoit_esphome/groups/delete", "group_id": group["id"]})
    assert msg["error"]["code"] == "not_found"


@pytest.mark.usefixtures("patch_sources")
async def test_hand_back_after_restart(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    """A restart mid-episode keeps the snapshots: clean air still restores the members."""
    calls = await _fake_fans(hass)
    _purifiers(hass)
    hass.states.async_set(
        "fan.bedroom",
        "on",
        {
            "preset_mode": "Manual",
            "preset_modes": PRESETS,
            "percentage": 100,
            "percentage_step": 25,
        },
    )
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {
            "groups": [{"id": "g1", "name": "Living room", "members": MEMBERS, "hold_min": 0}],
            "runtime": {
                "g1": {
                    "level": 1,
                    "snapshots": {
                        "fan.bedroom": {"state": "on", "preset_mode": "Sleep", "percentage": 25}
                    },
                }
            },
        },
    }
    await _setup(hass)
    await _settle(hass)
    # stored groups keep their sensors as saved: none here, so no number to go on
    assert hass.states.get(LEVEL).state == "0"
    assert calls == [("set_preset_mode", "fan.bedroom", {"preset_mode": "Sleep"})]


@pytest.mark.usefixtures("patch_sources")
async def test_group_fan(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    """The group as one fan: on / off is its control, Auto / Manual, speeds set the manual level."""
    _purifiers(hass)
    await _setup(hass)
    client = await hass_ws_client(hass)
    # no rising-fast jump: the level follows the thresholds
    await _save(client, members=MEMBERS, rise={"enabled": False})
    await _settle(hass)

    fan = hass.states.get(GROUP_FAN)
    assert fan.state == "on"
    assert fan.attributes["preset_modes"] == ["Auto", "Manual"]
    assert fan.attributes["preset_mode"] == "Auto"
    assert fan.attributes["percentage"] == 0  # clean air
    assert fan.attributes["percentage_step"] == 25

    _pm(hass, 60)  # level 3 in Auto
    await _settle(hass)
    assert hass.states.get(GROUP_FAN).attributes["percentage"] == 75

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": GROUP_FAN, "percentage": 50}, blocking=True
    )
    await _settle(hass)
    fan = hass.states.get(GROUP_FAN)
    assert fan.attributes["preset_mode"] == "Manual"
    assert fan.attributes["percentage"] == 50
    assert hass.states.get(LEVEL).state == "2"

    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": GROUP_FAN, "preset_mode": "Auto"}, blocking=True
    )
    await _settle(hass)
    assert hass.states.get(GROUP_FAN).attributes["preset_mode"] == "Auto"

    await hass.services.async_call("fan", "turn_off", {"entity_id": GROUP_FAN}, blocking=True)
    await _settle(hass)
    assert hass.states.get(GROUP_FAN).state == "off"
    assert hass.states.get(CONTROL).state == "off"

    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": GROUP_FAN, "percentage": 100}, blocking=True
    )
    await _settle(hass)
    fan = hass.states.get(GROUP_FAN)
    assert fan.state == "on"
    assert fan.attributes["preset_mode"] == "Manual"
    assert fan.attributes["percentage"] == 100
    assert hass.states.get(CONTROL).state == "on"

    msg = await _call(client, {"type": "levoit_esphome/groups/list"})
    (group,) = msg["result"]["groups"]
    assert (group["mode"], group["manual_level"], group["enabled"]) == ("manual", 4, True)


@pytest.mark.usefixtures("patch_sources")
async def test_group_air_quality(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    """0-4 from the worst sensor, in Manual and with the group off too."""
    _purifiers(hass)
    await _setup(hass)
    client = await hass_ws_client(hass)
    group = await _save(client, members=MEMBERS, max_speed=2)
    await _settle(hass)
    quality = hass.states.get(AIR_QUALITY)
    assert quality.state == "0"
    assert quality.attributes["sensor_levels"] == {
        "sensor.bedroom_pm25": 0,
        "sensor.living_pm25": 0,
    }

    _pm(hass, 60)  # level 3, above max speed 2
    await _settle(hass)
    quality = hass.states.get(AIR_QUALITY)
    assert quality.state == "3"
    assert quality.attributes["worst_sensor"] == "sensor.living_pm25"
    assert hass.states.get(LEVEL).state == "2"  # the group runs at its max

    await _save(client, id=group["id"], members=MEMBERS, max_speed=2, enabled=False)
    _pm(hass, 160)
    await _settle(hass)
    assert hass.states.get(AIR_QUALITY).state == "4"
    assert hass.states.get(LEVEL).state == "0"

    hass.states.async_set("sensor.bedroom_pm25", "unavailable")
    hass.states.async_set("sensor.living_pm25", "unavailable")
    await _settle(hass)
    assert hass.states.get(AIR_QUALITY).state == "unknown"
