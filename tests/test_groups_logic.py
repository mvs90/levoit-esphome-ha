"""Purifier groups: levels, speed mapping, hold and rising fast (no Home Assistant)."""

from __future__ import annotations

import pytest

from custom_components.levoit_esphome.groups_logic import (
    AQI,
    AQI_INDEX,
    DEFAULT_THRESHOLDS,
    ERR_INVALID,
    ERR_MEMBERS,
    ERR_THRESHOLDS,
    MODE_MANUAL,
    PM25,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    GroupError,
    GroupSensor,
    LevelKeeper,
    Reading,
    air_quality,
    allowed_speeds,
    member_speed,
    merge_sensors,
    parse_config,
    sensor_level,
    speed_count,
)

MEMBERS = ["fan.bedroom", "fan.living_room"]
MIN = 60


def _config(**changes):
    return parse_config({"id": "g1", "name": "Living room", "members": MEMBERS, **changes})


@pytest.mark.parametrize(
    ("max_speed", "speeds", "expected"),
    [
        (4, 4, [1, 2, 3, 4]),  # Core600S, Vital200S; Eleva 300X: 1, 2, 3, Turbo
        (4, 3, [1, 2, 2, 3]),  # Core200S, Core300S, Everest Air
        (4, 2, [1, 1, 2, 2]),
        (3, 3, [1, 2, 3]),
        (3, 4, [1, 2, 3]),
        (2, 4, [1, 2]),
        (1, 3, [1]),
    ],
)
def test_member_speed(max_speed: int, speeds: int, expected: list[int]) -> None:
    """Members with fewer speeds share levels; the top level is their fastest."""
    assert [member_speed(level, max_speed, speeds) for level in range(1, max_speed + 1)] == (
        expected
    )
    assert member_speed(0, max_speed, speeds) == 0
    # a level above max_speed (max_speed lowered) runs at the top speed
    assert member_speed(max_speed + 1, max_speed, speeds) == expected[-1]


def test_speed_count() -> None:
    """From the fan's percentage step; 4 when it has none."""
    assert speed_count(25) == 4
    assert speed_count(33.333333333333336) == 3
    assert speed_count(None) == 4
    assert speed_count("x") == 4
    assert speed_count(0) == 4


def test_sensor_level() -> None:
    """The highest level whose threshold the value meets."""
    pm25 = DEFAULT_THRESHOLDS[PM25]
    assert [sensor_level(v, pm25) for v in (0, 11.9, 12, 35, 54, 55, 150, 783)] == [
        0,
        0,
        1,
        2,
        2,
        3,
        4,
        4,
    ]
    # Levoit level: very good stays out, good 1, moderate 2, poor 4
    assert [sensor_level(v, DEFAULT_THRESHOLDS[AQI]) for v in (1, 2, 3, 4)] == [0, 1, 2, 4]
    assert [sensor_level(v, DEFAULT_THRESHOLDS[AQI_INDEX]) for v in (49, 50, 151, 500)] == [
        0,
        1,
        3,
        4,
    ]


def test_parse_defaults() -> None:
    """Defaults from the spec; as_dict round-trips."""
    config = _config()
    assert config.max_speed == 4
    assert config.hold_min == 10
    assert config.hand_back == "restore"
    assert config.mode == "auto"
    assert config.thresholds[AQI] == (2, 3, 4, 4)
    assert config.rise.pm25 == 20
    assert config.rise.aqi_index == 25
    assert parse_config(config.as_dict()) == config


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"members": ["fan.bedroom"]}, ERR_MEMBERS),
        ({"name": " "}, ERR_INVALID),
        ({"max_speed": 5}, ERR_INVALID),
        ({"max_speed": 2.5}, ERR_INVALID),
        ({"hand_back": "later"}, ERR_INVALID),
        ({"mode": "party"}, ERR_INVALID),
        ({"thresholds": {PM25: [12, 35, 30, 150]}}, ERR_THRESHOLDS),
        ({"thresholds": {PM25: [12, 35]}}, ERR_INVALID),
        ({"sensors": [{"entity_id": "sensor.x", "type": "co2"}]}, ERR_INVALID),
        ({"rise": {"pm25": -1}}, ERR_INVALID),
    ],
)
def test_parse_rejects(changes: dict, code: str) -> None:
    """What the editor would refuse to save."""
    with pytest.raises(GroupError) as err:
        _config(**changes)
    assert err.value.code == code


def test_parse_lenient_preview() -> None:
    """The preview takes an unfinished group."""
    config = parse_config({"members": ["fan.bedroom"]}, check_members=False)
    assert config.members == ("fan.bedroom",)
    assert config.name == ""


def test_parse_equal_thresholds_and_clamp() -> None:
    """Equal thresholds are allowed; manual_level follows a lower max_speed."""
    config = _config(thresholds={AQI: [2, 2, 3, 4]}, max_speed=2, manual_level=4)
    assert config.thresholds[AQI] == (2, 2, 3, 4)
    assert config.manual_level == 2


def test_merge_sensors() -> None:
    """Members' sensors minus removed ones, then the user's; no duplicates."""
    auto = [
        GroupSensor("sensor.bedroom_pm25", PM25),
        GroupSensor("sensor.bedroom_aqi", AQI),
        GroupSensor("sensor.living_pm25", PM25),
    ]
    chosen = [
        GroupSensor("sensor.old_member_pm25", PM25, SOURCE_AUTO),  # member left
        GroupSensor("sensor.hall_pm25", PM25, SOURCE_MANUAL),
        GroupSensor("sensor.living_pm25", PM25, SOURCE_MANUAL),
    ]
    merged = merge_sensors(auto, chosen, removed=["sensor.bedroom_aqi"])
    assert [(s.entity_id, s.source) for s in merged] == [
        ("sensor.bedroom_pm25", SOURCE_AUTO),
        ("sensor.living_pm25", SOURCE_AUTO),
        ("sensor.hall_pm25", SOURCE_MANUAL),
    ]


def _pm(value: float | None, entity_id: str = "sensor.pm25") -> list[Reading]:
    return [Reading(entity_id, PM25, value)]


def test_level_up_at_once_down_one_per_hold() -> None:
    """Raising never waits; lowering waits hold_min per level, one level at a time."""
    config = _config(rise={"enabled": False})
    keeper = LevelKeeper()
    keeper.step(config, _pm(5), 0)
    assert keeper.level == 0
    result = keeper.step(config, _pm(783), 10)
    assert keeper.level == 4
    assert result.worst is not None
    assert result.worst.value == 783
    keeper.step(config, _pm(5), 20)
    assert keeper.level == 4  # holds
    keeper.step(config, _pm(5), 10 + 10 * MIN)
    assert keeper.level == 3  # one step, not straight to 0
    keeper.step(config, _pm(5), 10 + 15 * MIN)
    assert keeper.level == 3
    keeper.step(config, _pm(40), 10 + 16 * MIN)
    assert keeper.level == 3  # target 2 < 3, hold not over
    keeper.step(config, _pm(60), 10 + 17 * MIN)
    assert keeper.level == 3  # target 3: stays, timer not reset
    keeper.step(config, _pm(5), 10 + 20 * MIN)
    assert keeper.level == 2
    for minutes in (30, 40):
        keeper.step(config, _pm(5), 10 + minutes * MIN)
    assert keeper.level == 0


def test_worst_sensor_wins_capped_at_max_speed() -> None:
    """The worst sensor sets the level, capped at max_speed."""
    config = _config(max_speed=3, rise={"enabled": False})
    keeper = LevelKeeper()
    result = keeper.step(
        config,
        [
            Reading("sensor.a", PM25, 20),  # level 1
            Reading("sensor.b", AQI, 4),  # level 4, capped at 3
            Reading("sensor.c", AQI_INDEX, None),  # skipped
        ],
        0,
    )
    assert keeper.level == 3
    assert result.worst is not None
    assert result.worst.entity_id == "sensor.b"
    assert result.levels == {"sensor.a": 1, "sensor.b": 3}
    assert result.usable == 2


def test_rising_fast() -> None:
    """A climb of rise.pm25 within the window jumps to max speed."""
    config = _config()
    keeper = LevelKeeper()
    keeper.step(config, _pm(8), 0)
    result = keeper.step(config, _pm(20), 2 * MIN)  # +12: level 1 only
    assert keeper.level == 1
    assert result.rising is None
    result = keeper.step(config, _pm(28), 4 * MIN)  # +20 in 4 minutes
    assert keeper.level == 4
    assert result.rising is not None


def test_rising_counts_from_value_before_window() -> None:
    """A sensor that sat still for long: the climb counts from its old value."""
    config = _config()
    keeper = LevelKeeper()
    keeper.step(config, _pm(5), 0)
    keeper.step(config, _pm(5), 60 * MIN)  # same value, no new sample needed
    keeper.step(config, _pm(30), 61 * MIN)
    assert keeper.level == 4


def test_slow_climb_is_not_rising() -> None:
    """The same climb over longer than the window is not rising fast."""
    config = _config()
    keeper = LevelKeeper()
    for minute, value in enumerate(range(5, 30, 2)):
        keeper.step(config, _pm(value), minute * 3 * MIN)
    assert keeper.level == 1  # 29 µg/m³: level 1


def test_no_data_holds_then_hands_back() -> None:
    """Every sensor unavailable: hold the level for hold_min, then level 0."""
    config = _config(rise={"enabled": False})
    keeper = LevelKeeper()
    keeper.step(config, _pm(60), 0)
    assert keeper.level == 3
    keeper.step(config, _pm(None), 1 * MIN)
    keeper.step(config, _pm(None), 10 * MIN)
    assert keeper.level == 3
    keeper.step(config, _pm(None), 11 * MIN)
    assert keeper.level == 0


def test_manual_then_auto_steps_down_at_once() -> None:
    """Manual sets its level; back in Auto the first step down does not wait."""
    keeper = LevelKeeper()
    keeper.manual(_config(mode=MODE_MANUAL, manual_level=3))
    assert keeper.level == 3
    config = _config(rise={"enabled": False})
    keeper.step(config, _pm(5), 0)
    assert keeper.level == 2
    keeper.step(config, _pm(5), 1 * MIN)
    assert keeper.level == 2  # now it holds


def test_acceptance_three_members() -> None:
    """PM2.5 at 783 with max speed 4: Core600S 4, Everest Air 3, Eleva Turbo (4)."""
    config = _config(members=["fan.core600s", "fan.everest", "fan.eleva"])
    keeper = LevelKeeper()
    keeper.step(config, _pm(783), 0)
    assert [member_speed(keeper.level, config.max_speed, n) for n in (4, 3, 4)] == [4, 3, 4]


def test_air_quality() -> None:
    """The worst sensor on the group's thresholds, 0-4, not capped by max speed."""
    config = _config(max_speed=2)
    quality = air_quality(
        config,
        [
            Reading("sensor.a", PM25, 40),  # level 2
            Reading("sensor.b", AQI, 4),  # level 4, above max speed 2
            Reading("sensor.c", AQI_INDEX, None),
        ],
    )
    assert quality.level == 4
    assert quality.worst is not None
    assert quality.worst.entity_id == "sensor.b"
    assert quality.levels == {"sensor.a": 2, "sensor.b": 4}
    assert air_quality(config, [Reading("sensor.a", PM25, 3)]).level == 0
    assert air_quality(config, [Reading("sensor.a", PM25, None)]).level is None
    assert air_quality(config, []).level is None


def test_member_max_speed() -> None:
    """A purifier limited to 2 spreads the levels over speeds 1 and 2."""
    config = _config(member_max_speed={"fan.bedroom": 2, "fan.gone": 1})
    assert config.member_max_speed == {"fan.bedroom": 2}  # members only
    assert parse_config(config.as_dict()) == config
    speeds = allowed_speeds(config, "fan.bedroom", 4)
    assert [member_speed(level, 4, speeds) for level in (1, 2, 3, 4)] == [1, 1, 2, 2]
    assert allowed_speeds(config, "fan.living_room", 3) == 3
    assert allowed_speeds(_config(member_max_speed={"fan.bedroom": 4}), "fan.bedroom", 3) == 3
    with pytest.raises(GroupError):
        _config(member_max_speed={"fan.bedroom": 5})
