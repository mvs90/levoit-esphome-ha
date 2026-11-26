"""Purifier groups: the rules, without Home Assistant.

A group ties two or more purifiers to shared air sensors. The sensors of one
type (PM1, PM2.5, PM10, the Levoit AQI level) are combined into one value, by
default the highest; each type's value gives a level from 1 (very good air) to
4 (poor), and the worst type sets the group level. Each member runs at a step
between its lowest (Off, Sleep or a speed) and its highest speed for that
level. The level goes up at once and down one step per hold time; without any
sensor value the group lets go and leaves the purifiers as they are.
groups.py runs this against Home Assistant states and services.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from statistics import fmean, median
from typing import Any

PM1 = "pm1"
PM25 = "pm25"
PM10 = "pm10"
AQI = "aqi"  # Levoit air quality level 1-4 (1 very good ... 4 poor), a level as it is
SENSOR_TYPES = (PM1, PM25, PM10, AQI)
THRESHOLD_TYPES = (PM1, PM25, PM10)
# earlier versions also had the Eleva's 0-500 index; a stored one is dropped
LEGACY_TYPES = ("aqi_index",)

SOURCE_AUTO = "auto"  # picked from a member
SOURCE_MANUAL = "manual"  # added by the user

MODE_AUTO = "auto"  # the sensors pick the level
MODE_MANUAL = "manual"  # the user picks one level for all members

# how the sensors of one type make one value
COMBINE_MAX = "max"
COMBINE_AVG = "avg"
COMBINE_MEDIAN = "median"
COMBINE_MIN = "min"
COMBINES = (COMBINE_MAX, COMBINE_AVG, COMBINE_MEDIAN, COMBINE_MIN)

# a member's steps: Off, Sleep (fans with that preset), then its speeds
STEP_OFF = "off"
STEP_SLEEP = "sleep"
type Step = int | str

MAX_LEVEL = 4
MIN_MEMBERS = 2
MAX_FAN_SPEEDS = 10

# Where levels 2, 3 and 4 start per sensor type, in µg/m³; level 1 is below.
# PM2.5 as the Levoit AQI ring (very good to 12, good to 35, moderate to 55),
# PM10 as the US AQI bands.
DEFAULT_THRESHOLDS: dict[str, tuple[float, ...]] = {
    PM1: (12, 35, 55),
    PM25: (12, 35, 55),
    PM10: (55, 155, 255),
}
THRESHOLD_COUNT = MAX_LEVEL - 1

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
    """Rising fast: a PM2.5 climb this big within the window jumps to level 4."""

    enabled: bool = True
    pm25: float = 20
    window_min: int = 5


@dataclass(frozen=True)
class MemberSpeeds:
    """A member's range in the group: level 1 runs at lowest, level 4 at highest."""

    lowest: Step = 1  # STEP_OFF, STEP_SLEEP or a speed
    highest: int | None = None  # None: its fastest speed

    def as_dict(self) -> dict[str, Any]:
        """As saved."""
        return {"lowest": self.lowest, "highest": self.highest}


DEFAULT_MEMBER_SPEEDS = MemberSpeeds()


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
    combine: Mapping[str, str] = field(
        default_factory=lambda: dict.fromkeys(SENSOR_TYPES, COMBINE_MAX)
    )
    thresholds: Mapping[str, tuple[float, ...]] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    rise: Rise = Rise()
    hold_min: int = 2
    turn_on: bool = True
    respect_manual: bool = True
    manual_pause_min: int = 30
    mode: str = MODE_AUTO
    manual_level: int = 1
    # per member: its lowest and highest step (absent: speed 1 to its fastest)
    member_speeds: Mapping[str, MemberSpeeds] = field(default_factory=dict)

    def speeds_of(self, member: str) -> MemberSpeeds:
        """A member's range (the default when it has none)."""
        return self.member_speeds.get(member, DEFAULT_MEMBER_SPEEDS)

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
            "combine": dict(self.combine),
            "thresholds": {t: list(self.thresholds[t]) for t in THRESHOLD_TYPES},
            "rise": {
                "enabled": self.rise.enabled,
                "pm25": self.rise.pm25,
                "window_min": self.rise.window_min,
            },
            "hold_min": self.hold_min,
            "turn_on": self.turn_on,
            "respect_manual": self.respect_manual,
            "manual_pause_min": self.manual_pause_min,
            "mode": self.mode,
            "manual_level": self.manual_level,
            "member_speeds": {m: s.as_dict() for m, s in self.member_speeds.items()},
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
    """Where levels 2-4 start per PM type.

    Earlier versions kept 4 values (where level 1 started, below it the group
    let go); the first one is dropped, so levels 2-4 start where they did.
    """
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise GroupError(ERR_INVALID, "thresholds must be per sensor type")
    result: dict[str, tuple[float, ...]] = {}
    for kind in THRESHOLD_TYPES:
        values = data.get(kind, DEFAULT_THRESHOLDS[kind])
        if isinstance(values, (list, tuple)) and len(values) == THRESHOLD_COUNT + 1:
            values = values[1:]
        if (
            not isinstance(values, (list, tuple))
            or len(values) != THRESHOLD_COUNT
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 for v in values)
        ):
            raise GroupError(
                ERR_INVALID, f"thresholds.{kind} must be {THRESHOLD_COUNT} numbers of 0 or more"
            )
        if any(b < a for a, b in pairwise(values)):
            raise GroupError(ERR_THRESHOLDS, f"thresholds.{kind} must rise from level 2 to 4")
        result[kind] = tuple(values)
    return result


def _combine(data: Any) -> dict[str, str]:
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise GroupError(ERR_INVALID, "combine must be per sensor type")
    return {kind: _choice(data, kind, COMBINE_MAX, COMBINES) for kind in SENSOR_TYPES}


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
        if item.get("type") in LEGACY_TYPES:
            continue
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


def _member_range(member: str, data: Any) -> MemberSpeeds:
    if not isinstance(data, Mapping):
        raise GroupError(ERR_INVALID, f"member_speeds.{member} must have lowest and highest")
    lowest = data.get("lowest", DEFAULT_MEMBER_SPEEDS.lowest)
    if lowest not in (STEP_OFF, STEP_SLEEP):
        lowest = _int(data, "lowest", 1, 1, MAX_FAN_SPEEDS)
    highest = data.get("highest")
    if highest is not None:
        highest = _int(data, "highest", MAX_FAN_SPEEDS, 1, MAX_FAN_SPEEDS)
    if isinstance(lowest, int) and highest is not None and lowest > highest:
        raise GroupError(ERR_INVALID, f"{member}: the lowest speed is above the highest")
    return MemberSpeeds(lowest, highest)


def _member_speeds(data: Mapping[str, Any], members: Iterable[str]) -> dict[str, MemberSpeeds]:
    """Per-member ranges, for members of the group only.

    Earlier versions had a group max speed and a highest speed per member
    (member_max_speed); a purifier's top speed was the lower of the two.
    """
    raw = data.get("member_speeds")
    if raw is None:
        max_speed = _int(data, "max_speed", MAX_LEVEL, 1, MAX_LEVEL)
        limits = data.get("member_max_speed")
        limits = limits if isinstance(limits, Mapping) else {}
        result: dict[str, MemberSpeeds] = {}
        for member in members:
            limit = limits.get(member)
            top = min(limit, max_speed) if isinstance(limit, int) else max_speed
            if top < MAX_LEVEL or isinstance(limit, int):
                result[member] = MemberSpeeds(1, max(1, top))
        return result
    if not isinstance(raw, Mapping):
        raise GroupError(ERR_INVALID, "member_speeds must be per purifier")
    ranges = {m: _member_range(m, raw[m]) for m in members if m in raw}
    return {m: r for m, r in ranges.items() if r != DEFAULT_MEMBER_SPEEDS}


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
    rise = data.get("rise") or {}
    if not isinstance(rise, Mapping):
        raise GroupError(ERR_INVALID, "rise must be an object")
    area_id = data.get("area_id")
    if area_id is not None and not isinstance(area_id, str):
        raise GroupError(ERR_INVALID, "area_id must be text")
    return GroupConfig(
        id=str(data.get("id") or ""),
        name=name.strip(),
        members=members,
        area_id=area_id or None,
        enabled=_bool(data, "enabled", True),
        sensors=_sensors(data.get("sensors")),
        removed_sensors=_entity_ids(data.get("removed_sensors"), "removed_sensors"),
        combine=_combine(data.get("combine")),
        thresholds=_thresholds(data.get("thresholds")),
        rise=Rise(
            enabled=_bool(rise, "enabled", True),
            pm25=_number(rise, "pm25", Rise.pm25),
            window_min=_int(rise, "window_min", Rise.window_min, 1, 60),
        ),
        hold_min=_int(data, "hold_min", 2, 0, 240),
        turn_on=_bool(data, "turn_on", True),
        respect_manual=_bool(data, "respect_manual", True),
        manual_pause_min=_int(data, "manual_pause_min", 30, 1, 1440),
        mode=_choice(data, "mode", MODE_AUTO, (MODE_AUTO, MODE_MANUAL)),
        manual_level=_int(data, "manual_level", 1, 1, MAX_LEVEL),
        member_speeds=_member_speeds(data, members),
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


def member_ladder(speeds: int, has_sleep: bool) -> list[Step]:
    """A member's steps, slowest first: Off, Sleep (if it has it), speeds 1 to N."""
    return [STEP_OFF, *([STEP_SLEEP] if has_sleep else []), *range(1, max(1, speeds) + 1)]


def _step_value(step: Step) -> int:
    """A step's speed, doubled to stay whole: Off 0, Sleep 1 (speed 0.5), speed n 2n."""
    if step == STEP_OFF:
        return 0
    if step == STEP_SLEEP:
        return 1
    return 2 * int(step)


def member_step(level: int, speeds: int, has_sleep: bool, rng: MemberSpeeds) -> Step | None:
    """The member's step for a group level; None at level 0 (let go).

    Level 1 runs at the lowest step and level 4 at the highest. With as many
    steps in the range as levels or fewer, each level takes the next step and
    the rest stay at the highest (s..3: Sleep, 1, 2, 3; 1..2: 1, 2, 2, 2). With
    more, levels 2 and 3 are spread evenly by speed, Sleep counting as 0.5, and
    rounded up to a step, so the bigger jumps are on the left (0..4: Off, 2, 3,
    4). A range the purifier cannot do is narrowed: Sleep without a Sleep preset
    is speed 1, speeds above its fastest are its fastest.
    """
    if level <= 0:
        return None
    ladder = member_ladder(speeds, has_sleep)
    top = ladder[-1]
    high = min(rng.highest or top, top)
    low: Step = rng.lowest
    if low == STEP_SLEEP and not has_sleep:
        low = 1
    if isinstance(low, int):
        low = min(low, high)
    steps = ladder[ladder.index(low) : ladder.index(high) + 1]
    index = min(level, MAX_LEVEL) - 1
    if len(steps) <= MAX_LEVEL:
        return steps[min(index, len(steps) - 1)]
    # the step at or above lowest + index * (highest - lowest) / (MAX_LEVEL - 1)
    v0, v1, gaps = _step_value(steps[0]), _step_value(steps[-1]), MAX_LEVEL - 1
    target = v0 * gaps + index * (v1 - v0)
    return next(step for step in steps if _step_value(step) * gaps >= target)


def type_level(config: GroupConfig, kind: str, value: float) -> int:
    """The level 1-4 a value of this type gives.

    The Levoit AQI level is the level; a PM value is 1 plus the number of the
    type's thresholds it meets.
    """
    if kind == AQI:
        return min(max(round(value), 1), MAX_LEVEL)
    return 1 + sum(1 for threshold in config.thresholds[kind] if value >= threshold)


def combine(values: Sequence[float], how: str) -> float:
    """One value from a type's sensors."""
    if how == COMBINE_MIN:
        return min(values)
    if how == COMBINE_AVG:
        return fmean(values)
    if how == COMBINE_MEDIAN:
        return median(values)
    return max(values)


@dataclass(frozen=True)
class Reading:
    """A group sensor's state now; value None while it has no number."""

    entity_id: str
    type: str
    value: float | None


@dataclass(frozen=True)
class TypeValue:
    """A sensor type's combined value and level."""

    type: str
    value: float
    level: int
    how: str  # the combine used; it makes no difference with one sensor
    sensors: tuple[str, ...]  # the sensors with a number
    top: str  # the sensor with the highest value


def type_values(config: GroupConfig, readings: Iterable[Reading]) -> list[TypeValue]:
    """Per sensor type with a number: its value, combined as the group says."""
    by_type: dict[str, list[Reading]] = {}
    for reading in readings:
        if reading.value is not None and reading.type in SENSOR_TYPES:
            by_type.setdefault(reading.type, []).append(reading)
    result: list[TypeValue] = []
    for kind in SENSOR_TYPES:
        if not (found := by_type.get(kind)):
            continue
        how = config.combine.get(kind, COMBINE_MAX)
        value = combine([r.value for r in found if r.value is not None], how)
        top = max(found, key=lambda r: r.value or 0)
        result.append(
            TypeValue(
                type=kind,
                value=value,
                level=type_level(config, kind, value),
                how=how,
                sensors=tuple(r.entity_id for r in found),
                top=top.entity_id,
            )
        )
    return result


def _sensor_levels(config: GroupConfig, readings: Iterable[Reading]) -> dict[str, int]:
    """Each sensor's own level, as if it were alone."""
    return {
        r.entity_id: type_level(config, r.type, r.value)
        for r in readings
        if r.value is not None and r.type in SENSOR_TYPES
    }


def _worst(values: Iterable[TypeValue]) -> TypeValue | None:
    worst: TypeValue | None = None
    for value in values:
        if worst is None or value.level > worst.level:
            worst = value
    return worst


@dataclass(frozen=True)
class Evaluation:
    """What the sensors ask for now."""

    target: int  # 1-4; 4 while rising fast; 0 without any sensor value
    levels: dict[str, int]  # per sensor with a number, on its own
    types: tuple[TypeValue, ...]  # per sensor type with a number
    worst: TypeValue | None  # the type that sets the target
    rising: Reading | None  # a PM2.5 sensor climbing fast, if any
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

    level: int | None  # 1-4; None while no sensor has a number
    worst: TypeValue | None
    levels: dict[str, int]  # per sensor with a number, on its own
    types: tuple[TypeValue, ...] = ()  # per sensor type with a number


def air_quality(config: GroupConfig, readings: Iterable[Reading]) -> AirQuality:
    """The worst type's level, 1-4, on the group's thresholds.

    What the air is like, not what the group does: no hold time, no rising
    fast, and the same in Manual or when disabled.
    """
    readings = list(readings)
    types = type_values(config, readings)
    worst = _worst(types)
    return AirQuality(
        level=worst.level if worst else None,
        worst=worst,
        levels=_sensor_levels(config, readings),
        types=tuple(types),
    )


def evaluate(config: GroupConfig, readings: Iterable[Reading], history: History) -> Evaluation:
    """The level the sensors ask for (Auto mode)."""
    readings = list(readings)
    types = type_values(config, readings)
    worst = _worst(types)
    rising: Reading | None = None
    if config.rise.enabled:
        rising = next(
            (
                r
                for r in readings
                if r.type == PM25
                and r.value is not None
                and history.climb(r.entity_id, r.value) >= config.rise.pm25
            ),
            None,
        )
    target = MAX_LEVEL if rising is not None else (worst.level if worst else 0)
    return Evaluation(
        target=target,
        levels=_sensor_levels(config, readings),
        types=tuple(types),
        worst=worst,
        rising=rising,
        usable=sum(1 for r in readings if r.value is not None and r.type in SENSOR_TYPES),
    )


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
        self.level = min(max(config.manual_level, 1), MAX_LEVEL)
        # back in Auto, the first evaluation may step down without waiting
        self.since = None
        self._no_data_since = None

    def step(
        self, config: GroupConfig, readings: list[Reading], now: float, *, now_level: bool = False
    ) -> Evaluation:
        """Evaluate the sensors and move the level (Auto mode).

        `now_level` (the editor's apply button) takes the sensors' level at
        once, down too, without waiting for the hold time.
        """
        self.history.add(readings, now, config.rise.window_min * 60)
        result = evaluate(config, readings, self.history)
        hold_s = config.hold_min * 60
        if result.usable == 0:
            # no numbers at all: hold the level for hold_min, then let go
            if self.level > 0:
                if self._no_data_since is None:
                    self._no_data_since = now
                if now - self._no_data_since >= hold_s:
                    self.level = 0
                    self.since = now
            return result
        self._no_data_since = None
        if result.target > self.level or (now_level and result.target != self.level):
            self.level = result.target
            self.since = now
        elif result.target < self.level and (self.since is None or now - self.since >= hold_s):
            self.level -= 1
            self.since = now
        elif self.since is None:
            self.since = now
        return result
