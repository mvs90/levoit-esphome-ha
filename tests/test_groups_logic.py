"""Purifier groups: levels, member steps, combining, hold and rising fast (no Home Assistant)."""

from __future__ import annotations

import pytest

from custom_components.levoit_esphome.groups_logic import (
    AQI,
    COMBINE_AVG,
    COMBINE_MAX,
    COMBINE_MEDIAN,
    COMBINE_MIN,
    DEFAULT_THRESHOLDS,
    ERR_INVALID,
    ERR_MEMBERS,
    ERR_THRESHOLDS,
    MODE_MANUAL,
    PM1,
    PM10,
    PM25,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    STEP_OFF,
    STEP_SLEEP,
    GroupError,
    GroupSensor,
    LevelKeeper,
    MemberSpeeds,
    Reading,
    air_quality,
    member_ladder,
    member_step,
    merge_sensors,
    parse_config,
    speed_count,
    type_level,
)

MEMBERS = ["fan.bedroom", "fan.living_room"]
MIN = 60


def _config(**changes):
    return parse_config({"id": "g1", "name": "Living room", "members": MEMBERS, **changes})


def _steps(speeds: int, sleep: bool, lowest=1, highest=None) -> list:
    rng = MemberSpeeds(lowest, highest)
    return [member_step(level, speeds, sleep, rng) for level in (1, 2, 3, 4)]


@pytest.mark.parametrize(
    ("speeds", "expected"),
    [
        (4, [1, 2, 3, 4]),  # Core600S, Vital200S; Eleva 300X: 1, 2, 3, Turbo; Everest + Turbo
        (3, [1, 2, 3, 3]),  # Core200S, Core300S
        (2, [1, 2, 2, 2]),
        (1, [1, 1, 1, 1]),
    ],
)
def test_member_step_default(speeds: int, expected: list[int]) -> None:
    """Speed 1 to the fastest: with fewer speeds than levels the top ones stay at the fastest."""
    assert _steps(speeds, True) == expected
    assert member_step(0, speeds, True, MemberSpeeds()) is None  # level 0: let go


def test_member_step_off_and_sleep() -> None:
    """Off or Sleep as the lowest step: level 1 runs there."""
    assert member_ladder(3, True) == [STEP_OFF, STEP_SLEEP, 1, 2, 3]
    assert member_ladder(3, False) == [STEP_OFF, 1, 2, 3]
    # more steps than levels: even by speed (Sleep 0.5), bigger jumps on the left
    assert _steps(4, True, STEP_OFF) == [STEP_OFF, 2, 3, 4]
    assert _steps(4, False, STEP_OFF) == [STEP_OFF, 2, 3, 4]
    assert _steps(4, True, STEP_SLEEP) == [STEP_SLEEP, 2, 3, 4]
    assert _steps(4, True, STEP_OFF, 3) == [STEP_OFF, 1, 2, 3]
    # as many steps as levels or fewer: one each, the rest at the highest
    assert _steps(3, True, STEP_SLEEP) == [STEP_SLEEP, 1, 2, 3]
    assert _steps(4, True, STEP_OFF, 2) == [STEP_OFF, STEP_SLEEP, 1, 2]
    assert _steps(3, True, STEP_SLEEP, 2) == [STEP_SLEEP, 1, 2, 2]
    assert _steps(3, True, STEP_SLEEP, 1) == [STEP_SLEEP, 1, 1, 1]
    assert _steps(3, True, STEP_OFF, 1) == [STEP_OFF, STEP_SLEEP, 1, 1]


def test_member_step_narrowed() -> None:
    """Sleep without the preset is speed 1; a range above the fan's speeds is cut."""
    assert _steps(3, False, STEP_SLEEP) == [1, 2, 3, 3]
    assert _steps(3, True, 2, 6) == [2, 3, 3, 3]
    assert _steps(3, True, 4) == [3, 3, 3, 3]
    assert _steps(4, True, 2, 3) == [2, 3, 3, 3]


def test_speed_count() -> None:
    """From the fan's percentage step; 4 when it has none."""
    assert speed_count(25) == 4
    assert speed_count(33.333333333333336) == 3
    assert speed_count(None) == 4
    assert speed_count("x") == 4
    assert speed_count(0) == 4


def test_type_level() -> None:
    """Level 1 below the first threshold; the Levoit AQI level is the level."""
    config = _config()
    assert [type_level(config, PM25, v) for v in (0, 11.9, 12, 35, 54, 55, 783)] == [
        1,
        1,
        2,
        3,
        3,
        4,
        4,
    ]
    assert [type_level(config, PM10, v) for v in (54, 55, 155, 300)] == [1, 2, 3, 4]
    assert [type_level(config, AQI, v) for v in (0, 1, 2, 3, 4, 5)] == [1, 1, 2, 3, 4, 4]


def test_parse_defaults() -> None:
    """Defaults; as_dict round-trips."""
    config = _config()
    assert config.hold_min == 2
    assert config.mode == "auto"
    assert config.thresholds == DEFAULT_THRESHOLDS
    assert config.combine == {
        PM1: COMBINE_MAX,
        PM25: COMBINE_MAX,
        PM10: COMBINE_MAX,
        AQI: COMBINE_MAX,
    }
    assert config.rise.pm25 == 20
    assert config.member_speeds == {}
    assert parse_config(config.as_dict()) == config


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"members": ["fan.bedroom"]}, ERR_MEMBERS),
        ({"name": " "}, ERR_INVALID),
        ({"manual_level": 5}, ERR_INVALID),
        ({"mode": "party"}, ERR_INVALID),
        ({"thresholds": {PM25: [35, 30, 150]}}, ERR_THRESHOLDS),
        ({"thresholds": {PM25: [12, 35]}}, ERR_INVALID),
        ({"thresholds": {PM10: [-1, 35, 50]}}, ERR_INVALID),
        ({"sensors": [{"entity_id": "sensor.x", "type": "co2"}]}, ERR_INVALID),
        ({"combine": {PM25: "sum"}}, ERR_INVALID),
        ({"rise": {"pm25": -1}}, ERR_INVALID),
        ({"member_speeds": {"fan.bedroom": {"lowest": 3, "highest": 2}}}, ERR_INVALID),
        ({"member_speeds": {"fan.bedroom": {"lowest": "turbo"}}}, ERR_INVALID),
        ({"member_speeds": {"fan.bedroom": {"highest": 0}}}, ERR_INVALID),
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


def test_parse_member_speeds() -> None:
    """Members only; the default range is not stored."""
    config = _config(
        member_speeds={
            "fan.bedroom": {"lowest": STEP_SLEEP, "highest": 3},
            "fan.living_room": {"lowest": 1, "highest": None},
            "fan.gone": {"lowest": STEP_OFF},
        }
    )
    assert config.member_speeds == {"fan.bedroom": MemberSpeeds(STEP_SLEEP, 3)}
    assert config.speeds_of("fan.living_room") == MemberSpeeds()
    assert parse_config(config.as_dict()) == config


def test_parse_earlier_version() -> None:
    """A group saved by 0.6: AQI index dropped, levels 2-4 kept, max speeds as highest."""
    config = _config(
        max_speed=3,
        member_max_speed={"fan.bedroom": 2},
        thresholds={PM25: [12, 35, 55, 150], "aqi": [2, 3, 4, 4], "aqi_index": [50, 100, 150, 200]},
        sensors=[
            {"entity_id": "sensor.eleva_aqi", "type": "aqi_index", "source": "auto"},
            {"entity_id": "sensor.hall_pm25", "type": PM25, "source": "manual"},
        ],
        rise={"enabled": True, "pm25": 15, "aqi_index": 25, "window_min": 5},
        manual_level=3,
    )
    assert config.thresholds[PM25] == (35, 55, 150)
    assert [s.entity_id for s in config.sensors] == ["sensor.hall_pm25"]
    assert config.member_speeds == {
        "fan.bedroom": MemberSpeeds(1, 2),
        "fan.living_room": MemberSpeeds(1, 3),
    }
    assert config.rise.pm25 == 15
    assert config.manual_level == 3
    # all speeds before: nothing to store
    assert _config(max_speed=4).member_speeds == {}


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
    config = _config(rise={"enabled": False}, hold_min=10)
    keeper = LevelKeeper()
    keeper.step(config, _pm(5), 0)
    assert keeper.level == 1  # very good air: level 1, not let go
    result = keeper.step(config, _pm(783), 10)
    assert keeper.level == 4
    assert result.worst is not None
    assert result.worst.value == 783
    keeper.step(config, _pm(5), 20)
    assert keeper.level == 4  # holds
    keeper.step(config, _pm(5), 10 + 10 * MIN)
    assert keeper.level == 3  # one step at a time
    keeper.step(config, _pm(5), 10 + 15 * MIN)
    assert keeper.level == 3
    keeper.step(config, _pm(40), 10 + 16 * MIN)
    assert keeper.level == 3  # target 3: stays, timer not reset
    keeper.step(config, _pm(5), 10 + 20 * MIN)
    assert keeper.level == 2
    for minutes in (30, 40, 50):
        keeper.step(config, _pm(5), 10 + minutes * MIN)
    assert keeper.level == 1  # never below level 1 while a sensor has a value


def test_now_level_skips_the_hold() -> None:
    """The apply button: the sensors' level at once, down too."""
    config = _config(rise={"enabled": False}, hold_min=10)
    keeper = LevelKeeper()
    keeper.step(config, _pm(783), 0)
    keeper.step(config, _pm(20), 1 * MIN, now_level=True)
    assert keeper.level == 2


def test_worst_type_wins() -> None:
    """Each type's value sets its level; the worst type sets the group's."""
    config = _config(rise={"enabled": False})
    keeper = LevelKeeper()
    result = keeper.step(
        config,
        [
            Reading("sensor.a", PM25, 20),  # level 2
            Reading("sensor.b", AQI, 3),  # level 3
            Reading("sensor.c", PM10, None),  # skipped
        ],
        0,
    )
    assert keeper.level == 3
    assert result.worst is not None
    assert result.worst.type == AQI
    assert result.worst.top == "sensor.b"
    assert result.levels == {"sensor.a": 2, "sensor.b": 3}
    assert result.usable == 2


@pytest.mark.parametrize(
    ("how", "value", "level"),
    [
        (COMBINE_MAX, 60, 4),
        (COMBINE_AVG, 30, 2),
        (COMBINE_MEDIAN, 20, 2),
        (COMBINE_MIN, 10, 1),
    ],
)
def test_combine(how: str, value: float, level: int) -> None:
    """Several sensors of one type make one value, as the group says."""
    config = _config(rise={"enabled": False}, combine={PM25: how})
    readings = [
        Reading("sensor.a", PM25, 10),
        Reading("sensor.b", PM25, 20),
        Reading("sensor.c", PM25, 60),
        Reading("sensor.d", PM25, None),
    ]
    result = LevelKeeper().step(config, readings, 0)
    assert result.worst is not None
    assert result.worst.value == value
    assert result.worst.level == level
    assert result.worst.sensors == ("sensor.a", "sensor.b", "sensor.c")
    assert result.worst.top == "sensor.c"
    assert result.target == level
    # each sensor's own level stays as if it were alone
    assert result.levels == {"sensor.a": 1, "sensor.b": 2, "sensor.c": 4}


def test_rising_fast() -> None:
    """A PM2.5 climb of rise.pm25 within the window jumps to level 4."""
    config = _config()
    keeper = LevelKeeper()
    keeper.step(config, _pm(8), 0)
    result = keeper.step(config, _pm(20), 2 * MIN)  # +12: level 2 only
    assert keeper.level == 2
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
    assert keeper.level == 2  # 29 µg/m³: level 2


def test_no_data_holds_then_lets_go() -> None:
    """Every sensor unavailable: hold the level for hold_min, then level 0."""
    config = _config(rise={"enabled": False}, hold_min=10)
    keeper = LevelKeeper()
    keeper.step(config, _pm(40), 0)
    assert keeper.level == 3
    keeper.step(config, _pm(None), 1 * MIN)
    keeper.step(config, _pm(None), 10 * MIN)
    assert keeper.level == 3
    keeper.step(config, _pm(None), 11 * MIN)
    assert keeper.level == 0


def test_manual_then_auto_steps_down_at_once() -> None:
    """Manual sets its level; back in Auto the first step down does not wait."""
    keeper = LevelKeeper()
    keeper.manual(_config(mode=MODE_MANUAL, manual_level=4))
    assert keeper.level == 4
    config = _config(rise={"enabled": False})
    keeper.step(config, _pm(5), 0)
    assert keeper.level == 3
    keeper.step(config, _pm(5), 1 * MIN)
    assert keeper.level == 3  # now it holds


def test_air_quality() -> None:
    """The worst type on the group's thresholds, 1-4."""
    config = _config()
    quality = air_quality(
        config,
        [
            Reading("sensor.a", PM25, 40),  # level 3
            Reading("sensor.b", AQI, 4),  # level 4
            Reading("sensor.c", PM1, None),
        ],
    )
    assert quality.level == 4
    assert quality.worst is not None
    assert quality.worst.top == "sensor.b"
    assert quality.levels == {"sensor.a": 3, "sensor.b": 4}
    assert air_quality(config, [Reading("sensor.a", PM25, 3)]).level == 1
    assert air_quality(config, [Reading("sensor.a", PM25, None)]).level is None
    assert air_quality(config, []).level is None
