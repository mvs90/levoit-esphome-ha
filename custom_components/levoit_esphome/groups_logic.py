"""Purifier groups: the rules, without Home Assistant.

A group ties two or more purifiers to shared air sensors. Each sensor's reading
gives a level from its type's four thresholds; the worst sensor sets the group
level, and every member runs at its own speed for that level. The level goes up
at once and down one step per hold time. groups.py runs this against Home
Assistant states and services.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

PM25 = "pm25"
AQI = "aqi"  # Levoit air quality level 1-4 (1 very good ... 4 poor)
AQI_INDEX = "aqi_index"  # 0-500 index (Eleva 300X)
SENSOR_TYPES = (PM25, AQI, AQI_INDEX)

SOURCE_AUTO = "auto"  # picked from a member
SOURCE_MANUAL = "manual"  # added by the user

MODE_AUTO = "auto"  # the sensors pick the level
MODE_MANUAL = "manual"  # the user picks one level for all members

HAND_BACK_RESTORE = "restore"
HAND_BACK_AUTO = "auto"
HAND_BACK_SLEEP = "sleep"
HAND_BACK_LOW = "low"
HAND_BACK_OFF = "off"
HAND_BACK = (HAND_BACK_RESTORE, HAND_BACK_AUTO, HAND_BACK_SLEEP, HAND_BACK_LOW, HAND_BACK_OFF)

MAX_LEVEL = 4
MIN_MEMBERS = 2

# Start of levels 1-4 per sensor type. The Levoit level: Good starts level 1,
# Moderate level 2, Poor level 4.
DEFAULT_THRESHOLDS: dict[str, tuple[float, ...]] = {
    PM25: (12, 35, 55, 150),
    AQI: (2, 3, 4, 4),
    AQI_INDEX: (50, 100, 150, 200),
}

ERR_INVALID = "invalid"
ERR_MEMBERS = "members"
ERR_THRESHOLDS = "thresholds"


class GroupError(ValueError):
    """A group config that cannot be saved."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GroupSensor:
    """An air sensor of a group."""

    entity_id: str
    type: str
    source: str = SOURCE_AUTO


@dataclass(frozen=True)
class Rise:
    """Rising fast: a climb this big within the window jumps to max speed."""

    enabled: bool = True
    pm25: float = 20
    aqi_index: float = 25
    window_min: int = 5


@dataclass(frozen=True)
class GroupConfig:
    """One purifier group, as saved."""

    id: str
    name: str
    members: tuple[str, ...]
    area_id: str | None = None
    enabled: bool = True
    sensors: tuple[GroupSensor, ...] = ()
    removed_sensors: tuple[str, ...] = ()
    max_speed: int = MAX_LEVEL
    thresholds: Mapping[str, tuple[float, ...]] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    rise: Rise = Rise()
    hold_min: int = 2
    hand_back: str = HAND_BACK_RESTORE
    turn_on: bool = True
    respect_manual: bool = True
    manual_pause_min: int = 30
    mode: str = MODE_AUTO
    manual_level: int = 1
    # per member: its highest speed in this group (absent: all its speeds)
    member_max_speed: Mapping[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """The config as saved and sent to the panel."""
        return {
            "id": self.id,
            "name": self.name,
            "area_id": self.area_id,
            "enabled": self.enabled,
            "members": list(self.members),
            "sensors": [
                {"entity_id": s.entity_id, "type": s.type, "source": s.source} for s in self.sensors
            ],
            "removed_sensors": list(self.removed_sensors),
            "max_speed": self.max_speed,
            "thresholds": {t: list(self.thresholds[t]) for t in SENSOR_TYPES},
            "rise": {
                "enabled": self.rise.enabled,
                "pm25": self.rise.pm25,
                "aqi_index": self.rise.aqi_index,
                "window_min": self.rise.window_min,
            },
            "hold_min": self.hold_min,
            "hand_back": self.hand_back,
            "turn_on": self.turn_on,
            "respect_manual": self.respect_manual,
            "manual_pause_min": self.manual_pause_min,
            "mode": self.mode,
            "manual_level": self.manual_level,
            "member_max_speed": dict(self.member_max_speed),
        }


def _int(data: Mapping[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise GroupError(ERR_INVALID, f"{key} must be a whole number")
    if not low <= value <= high:
        raise GroupError(ERR_INVALID, f"{key} must be {low} to {high}")
    return int(value)


def _number(data: Mapping[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise GroupError(ERR_INVALID, f"{key} must be a number of 0 or more")
    return value


def _bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise GroupError(ERR_INVALID, f"{key} must be true or false")
    return value


def _choice(data: Mapping[str, Any], key: str, default: str, choices: Iterable[str]) -> str:
    value = data.get(key, default)
    if value not in choices:
        raise GroupError(ERR_INVALID, f"{key} must be one of {', '.join(choices)}")
    return value


def _thresholds(data: Any) -> dict[str, tuple[float, ...]]:
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise GroupError(ERR_INVALID, "thresholds must be per sensor type")
    result: dict[str, tuple[float, ...]] = {}
    for kind in SENSOR_TYPES:
        values = data.get(kind, DEFAULT_THRESHOLDS[kind])
        if (
            not isinstance(values, (list, tuple))
            or len(values) != MAX_LEVEL
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values)
        ):
            raise GroupError(ERR_INVALID, f"thresholds.{kind} must be {MAX_LEVEL} numbers")
        if any(b < a for a, b in pairwise(values)):
            raise GroupError(
                ERR_THRESHOLDS, f"thresholds.{kind} must rise from level 1 to {MAX_LEVEL}"
            )
        result[kind] = tuple(values)
    return result


def _sensors(data: Any) -> tuple[GroupSensor, ...]:
    if data is None:
        return ()
    if not isinstance(data, (list, tuple)):
        raise GroupError(ERR_INVALID, "sensors must be a list")
    sensors: list[GroupSensor] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, Mapping) or not isinstance(item.get("entity_id"), str):
            raise GroupError(ERR_INVALID, "each sensor needs an entity_id")
        kind = _choice(item, "type", "", SENSOR_TYPES)
        source = _choice(item, "source", SOURCE_MANUAL, (SOURCE_AUTO, SOURCE_MANUAL))
        if item["entity_id"] in seen:
            continue
        seen.add(item["entity_id"])
        sensors.append(GroupSensor(item["entity_id"], kind, source))
    return tuple(sensors)


def _entity_ids(data: Any, key: str) -> tuple[str, ...]:
    if data is None:
        return ()
    if not isinstance(data, (list, tuple)) or not all(isinstance(e, str) for e in data):
        raise GroupError(ERR_INVALID, f"{key} must be a list of entity ids")
    return tuple(dict.fromkeys(data))


def _member_max(data: Any, members: Iterable[str]) -> dict[str, int]:
    """Per-member speed limits, for members of the group only."""
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise GroupError(ERR_INVALID, "member_max_speed must be per purifier")
    limits: dict[str, int] = {}
    for member in members:
        if member in data:
            limits[member] = _int(data, member, MAX_LEVEL, 1, MAX_LEVEL)
    return limits


def parse_config(data: Mapping[str, Any], *, check_members: bool = True) -> GroupConfig:
    """A group config from what the panel sends or the store holds.

    Raises GroupError. `check_members=False` lets an unfinished group through
    (the editor's preview).
    """
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        if check_members:
            raise GroupError(ERR_INVALID, "The group needs a name")
        name = ""
    members = _entity_ids(data.get("members"), "members")
    if check_members and len(members) < MIN_MEMBERS:
        raise GroupError(ERR_MEMBERS, f"Pick at least {MIN_MEMBERS} purifiers")
    max_speed = _int(data, "max_speed", MAX_LEVEL, 1, MAX_LEVEL)
    rise = data.get("rise") or {}
    if not isinstance(rise, Mapping):
        raise GroupError(ERR_INVALID, "rise must be an object")
    area_id = data.get("area_id")
    if area_id is not None and not isinstance(area_id, str):
        raise GroupError(ERR_INVALID, "area_id must be text")
    manual_level = data.get("manual_level", 1)
    if isinstance(manual_level, (int, float)) and not isinstance(manual_level, bool):
        # clamped when max_speed drops
        manual_level = min(max(int(manual_level), 1), max_speed)
    return GroupConfig(
        id=str(data.get("id") or ""),
        name=name.strip(),
        members=members,
        area_id=area_id or None,
        enabled=_bool(data, "enabled", True),
        sensors=_sensors(data.get("sensors")),
        removed_sensors=_entity_ids(data.get("removed_sensors"), "removed_sensors"),
        max_speed=max_speed,
        thresholds=_thresholds(data.get("thresholds")),
        rise=Rise(
            enabled=_bool(rise, "enabled", True),
            pm25=_number(rise, "pm25", Rise.pm25),
            aqi_index=_number(rise, "aqi_index", Rise.aqi_index),
            window_min=_int(rise, "window_min", Rise.window_min, 1, 60),
        ),
        hold_min=_int(data, "hold_min", 2, 0, 240),
        hand_back=_choice(data, "hand_back", HAND_BACK_RESTORE, HAND_BACK),
        turn_on=_bool(data, "turn_on", True),
        respect_manual=_bool(data, "respect_manual", True),
        manual_pause_min=_int(data, "manual_pause_min", 30, 1, 1440),
        mode=_choice(data, "mode", MODE_AUTO, (MODE_AUTO, MODE_MANUAL)),
        manual_level=_int({"manual_level": manual_level}, "manual_level", 1, 1, max_speed),
        member_max_speed=_member_max(data.get("member_max_speed"), members),
    )


def merge_sensors(
    auto: Iterable[GroupSensor],
    chosen: Iterable[GroupSensor],
    removed: Iterable[str],
) -> tuple[GroupSensor, ...]:
    """The group's sensors: its members' (minus removed ones), then the user's own.

    Auto sensors of former members drop out; ones the user added stay.
    """
    removed_ids = set(removed)
    result: dict[str, GroupSensor] = {}
    for sensor in auto:
        if sensor.entity_id not in removed_ids:
            result.setdefault(sensor.entity_id, GroupSensor(sensor.entity_id, sensor.type))
    for sensor in chosen:
        if sensor.source == SOURCE_MANUAL and sensor.entity_id not in result:
            result[sensor.entity_id] = sensor
    return tuple(result.values())


def speed_count(percentage_step: Any) -> int:
    """A fan's number of speeds from its percentage step (100 / step)."""
    try:
        step = float(percentage_step)
    except (TypeError, ValueError):
        return MAX_LEVEL
    if step <= 0:
        return MAX_LEVEL
    return max(1, round(100 / step))


def allowed_speeds(config: GroupConfig, member: str, speeds: int) -> int:
    """How many of a member's speeds the group may use (its limit, if lower)."""
    limit = config.member_max_speed.get(member)
    return min(speeds, limit) if limit else speeds


def member_speed(level: int, max_speed: int, speeds: int) -> int:
    """The member's speed for a group level; 0 for level 0.

    A member with fewer speeds than max_speed shares levels, so the top level
    is always its fastest speed: 1 + round((L - 1)(N - 1) / (M - 1)), half up.
    """
    if level <= 0:
        return 0
    level = min(level, max_speed)
    if max_speed <= 1:
        return 1
    if max_speed <= speeds:
        return level
    numerator = (level - 1) * (speeds - 1)
    denominator = max_speed - 1
    return 1 + (2 * numerator + denominator) // (2 * denominator)


def sensor_level(value: float, thresholds: Iterable[float]) -> int:
    """Highest level whose threshold the value meets (0 below level 1)."""
    return sum(1 for threshold in thresholds if value >= threshold)


@dataclass(frozen=True)
class Reading:
    """A group sensor's state now; value None while it has no number."""

    entity_id: str
    type: str
    value: float | None


@dataclass(frozen=True)
class Evaluation:
    """What the sensors ask for now."""

    target: int  # capped at max_speed; max_speed while rising fast
    levels: dict[str, int]  # per usable sensor
    worst: Reading | None  # the sensor that sets the target
    rising: Reading | None  # a sensor climbing fast, if any
    usable: int  # sensors with a number


class History:
    """Recent readings per sensor, for the rising-fast rule."""

    def __init__(self) -> None:
        """Initialize."""
        self._samples: dict[str, deque[tuple[float, float]]] = {}

    def add(self, readings: Iterable[Reading], now: float, window_s: float) -> None:
        """Record the readings and forget what the window no longer needs.

        The newest sample from before the window stays: it is the value the
        sensor had when the window opened.
        """
        for reading in readings:
            if reading.value is None:
                continue
            samples = self._samples.setdefault(reading.entity_id, deque())
            if not samples or samples[-1] != (now, reading.value):
                samples.append((now, reading.value))
        start = now - window_s
        for entity_id in list(self._samples):
            samples = self._samples[entity_id]
            while len(samples) > 1 and samples[1][0] <= start:
                samples.popleft()

    def climb(self, entity_id: str, value: float) -> float:
        """How far the value is above the lowest one in the window."""
        samples = self._samples.get(entity_id)
        if not samples:
            return 0
        return value - min(v for _, v in samples)


@dataclass(frozen=True)
class AirQuality:
    """The group's air quality on its own thresholds."""

    level: int | None  # 0 (below level 1) to 4; None while no sensor has a number
    worst: Reading | None
    levels: dict[str, int]  # per sensor with a number


def air_quality(config: GroupConfig, readings: Iterable[Reading]) -> AirQuality:
    """The worst sensor's level, 0-4, on the group's thresholds.

    What the air is like, not what the group does: no hold time, no rising
    fast, not capped at max_speed, and the same in Manual or when disabled.
    """
    levels: dict[str, int] = {}
    worst: Reading | None = None
    worst_level = -1
    for reading in readings:
        if reading.value is None or reading.type not in config.thresholds:
            continue
        level = sensor_level(reading.value, config.thresholds[reading.type])
        levels[reading.entity_id] = level
        if level > worst_level:
            worst, worst_level = reading, level
    return AirQuality(level=worst_level if levels else None, worst=worst, levels=levels)


def evaluate(config: GroupConfig, readings: Iterable[Reading], history: History) -> Evaluation:
    """The level the sensors ask for (Auto mode)."""
    levels: dict[str, int] = {}
    worst: Reading | None = None
    worst_level = -1
    rising: Reading | None = None
    usable = 0
    for reading in readings:
        if reading.value is None or reading.type not in config.thresholds:
            continue
        usable += 1
        level = min(sensor_level(reading.value, config.thresholds[reading.type]), config.max_speed)
        levels[reading.entity_id] = level
        if level > worst_level:
            worst, worst_level = reading, level
        if config.rise.enabled and rising is None:
            limit = {PM25: config.rise.pm25, AQI_INDEX: config.rise.aqi_index}.get(reading.type)
            if limit is not None and history.climb(reading.entity_id, reading.value) >= limit:
                rising = reading
    target = config.max_speed if rising is not None else max(worst_level, 0)
    return Evaluation(target=target, levels=levels, worst=worst, rising=rising, usable=usable)


class LevelKeeper:
    """The group's current level: up at once, down one level per hold time."""

    def __init__(self, level: int = 0, since: float | None = None) -> None:
        """Initialize; `since` None lets the next evaluation step down at once."""
        self.level = level
        self.since = since
        self.history = History()
        self._no_data_since: float | None = None

    def manual(self, config: GroupConfig) -> None:
        """Manual mode: the user's level, for all members."""
        self.level = min(max(config.manual_level, 1), config.max_speed)
        # back in Auto, the first evaluation may step down without waiting
        self.since = None
        self._no_data_since = None

    def step(self, config: GroupConfig, readings: list[Reading], now: float) -> Evaluation:
        """Evaluate the sensors and move the level (Auto mode)."""
        self.history.add(readings, now, config.rise.window_min * 60)
        result = evaluate(config, readings, self.history)
        hold_s = config.hold_min * 60
        if result.usable == 0:
            # no numbers at all: hold the level for hold_min, then hand back
            if self.level > 0:
                if self._no_data_since is None:
                    self._no_data_since = now
                if now - self._no_data_since >= hold_s:
                    self.level = 0
                    self.since = now
            return result
        self._no_data_since = None
        if result.target > self.level:
            self.level = result.target
            self.since = now
        elif result.target < self.level and (self.since is None or now - self.since >= hold_s):
            self.level -= 1
            self.since = now
        elif self.since is None:
            self.since = now
        return result
