"""Purifier groups in Home Assistant: stored groups and the loop that runs them.

The rules (levels, speed mapping, hold, rising fast) are in groups_logic.py.
Here each enabled group follows its sensors and members, puts the members in
Manual at their speed for the group level, and hands them back when the air is
clean again. Changes the group made carry its own Context; any other change to a
member it controls is a person's, and pauses the group for that member.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import logging
import math
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STOP,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.percentage import ranged_value_to_percentage

from .const import DOMAIN
from .controls import match_controls
from .groups_logic import (
    AQI,
    AQI_INDEX,
    ERR_MEMBERS,
    HAND_BACK_AUTO,
    HAND_BACK_LOW,
    HAND_BACK_OFF,
    HAND_BACK_SLEEP,
    MODE_AUTO,
    MODE_MANUAL,
    PM25,
    Evaluation,
    GroupConfig,
    GroupError,
    GroupSensor,
    History,
    LevelKeeper,
    Reading,
    evaluate,
    member_speed,
    merge_sensors,
    parse_config,
    speed_count,
)

if TYPE_CHECKING:
    from .coordinator import LevoitEsphomeCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.groups"
STORAGE_VERSION = 1
SAVE_DELAY = 10
TICK = timedelta(seconds=30)

# a group added (its entities are created)
SIGNAL_GROUPS = f"{DOMAIN}_groups"

ERR_NOT_FOUND = "not_found"

PRESET_MANUAL = "Manual"
PRESET_AUTO = "Auto"
PRESET_SLEEP = "Sleep"

# controls.py keys of a purifier's air sensors
SENSOR_KEYS = {"sensor.pm25": PM25, "sensor.aqi": AQI, "sensor.aqi_index": AQI_INDEX}
TYPE_LABELS = {PM25: "PM2.5", AQI: "Air quality", AQI_INDEX: "AQI"}
AQI_WORDS = {1: "Very good", 2: "Good", 3: "Moderate", 4: "Poor"}

STATUS_PAUSED = "paused"  # control switch off
STATUS_MANUAL = "manual"  # the user's level for all members
STATUS_IN_CONTROL = "in_control"
STATUS_WATCHING = "watching"  # air is clean
STATUS_NO_SENSORS = "no_sensors"  # no sensor with a number: never takes control

OFFLINE = (STATE_UNAVAILABLE, STATE_UNKNOWN)


def signal_group(group_id: str) -> str:
    """Dispatcher signal: this group's config or state changed."""
    return f"{DOMAIN}_group_{group_id}"


def group_identifier(group_id: str) -> tuple[str, str]:
    """Device registry identifier of a group's device."""
    return (DOMAIN, f"group_{group_id}")


def _now() -> float:
    return dt_util.utcnow().timestamp()


def _iso(timestamp: float | None) -> str | None:
    return dt_util.utc_from_timestamp(timestamp).isoformat() if timestamp is not None else None


@dataclass(frozen=True)
class LevoitFan:
    """A purifier that can be in a group: the fan of a Levoit device."""

    entity_id: str
    name: str
    title: str
    model: str | None
    device_id: str
    area_id: str | None
    sensors: tuple[GroupSensor, ...]


def _number(state: State | None) -> float | None:
    if state is None:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _fan_view(state: State) -> tuple[Any, ...]:
    """What a group sets on a member: power, mode and speed."""
    return (
        state.state,
        state.attributes.get(ATTR_PRESET_MODE),
        state.attributes.get(ATTR_PERCENTAGE),
    )


def _current_speed(state: State) -> int:
    """The member's speed now (0 while off)."""
    if state.state != STATE_ON:
        return 0
    speeds = speed_count(state.attributes.get(ATTR_PERCENTAGE_STEP))
    percentage = state.attributes.get(ATTR_PERCENTAGE) or 0
    return round(percentage * speeds / 100)


def _in_manual(state: State) -> bool:
    """In Manual, or a fan without modes."""
    presets = state.attributes.get(ATTR_PRESET_MODES) or []
    return not presets or state.attributes.get(ATTR_PRESET_MODE) in (None, PRESET_MANUAL)


class GroupManager:
    """The purifier groups: stored config, one runner per group."""

    def __init__(self, hass: HomeAssistant, coordinator: LevoitEsphomeCoordinator) -> None:
        """Initialize."""
        self.hass = hass
        self.coordinator = coordinator
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.groups: dict[str, GroupConfig] = {}
        self.dismissed_areas: list[str] = []
        # level and member snapshots of groups that are not running (saved)
        self._runtime: dict[str, dict[str, Any]] = {}
        self._runners: dict[str, GroupRunner] = {}
        self._listeners: list[Callable[[], None]] = []
        self._started = False

    # ---- storage ----

    async def async_load(self) -> None:
        """Read the groups and the snapshots of a hand back still to do."""
        data = await self._store.async_load() or {}
        for raw in data.get("groups", []):
            try:
                config = parse_config(raw, check_members=False)
            except GroupError as err:
                _LOGGER.warning("Skipping a stored purifier group: %s", err)
                continue
            if config.id:
                self.groups[config.id] = config
        self.dismissed_areas = [a for a in data.get("dismissed_areas", []) if isinstance(a, str)]
        runtime = data.get("runtime")
        if isinstance(runtime, dict):
            self._runtime = {k: v for k, v in runtime.items() if k in self.groups}

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        runtime = dict(self._runtime)
        for group_id, runner in self._runners.items():
            runtime[group_id] = runner.runtime()
        return {
            "groups": [config.as_dict() for config in self.groups.values()],
            "dismissed_areas": self.dismissed_areas,
            "runtime": {k: v for k, v in runtime.items() if v.get("snapshots")},
        }

    @callback
    def async_schedule_save(self) -> None:
        """Save soon (level and snapshots changed)."""
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)

    async def _async_save(self) -> None:
        await self._store.async_save(self._data_to_save())

    # ---- running ----

    @callback
    def async_start(self, _hass: HomeAssistant | None = None) -> None:
        """Run every group (once Home Assistant has started)."""
        self._started = True
        for config in self.groups.values():
            self._start_runner(config)

    @callback
    def async_stop_with_hass(self) -> CALLBACK_TYPE:
        """Stop the groups when Home Assistant stops; returns the unsubscribe."""
        fired = False

        @callback
        def _stop(_event: Event) -> None:
            nonlocal fired
            fired = True
            self.async_stop()

        unsub = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)

        @callback
        def _unsub() -> None:
            if not fired:
                unsub()

        return _unsub

    @callback
    def async_stop(self) -> None:
        """Stop all groups (unload, shutdown); a hand back still to do is kept for later."""
        self._started = False
        for group_id, runner in self._runners.items():
            self._runtime[group_id] = runner.runtime()
            runner.stop()
        self._runners.clear()
        self._store.async_delay_save(self._data_to_save, 0)

    @callback
    def _start_runner(self, config: GroupConfig) -> None:
        runner = GroupRunner(self, config, self._runtime.pop(config.id, None))
        self._runners[config.id] = runner
        runner.start()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `listener` whenever a group or its state changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def async_notify(self, group_id: str | None = None) -> None:
        """A group (or the list) changed: entities and panels follow."""
        if group_id is not None:
            async_dispatcher_send(self.hass, signal_group(group_id))
        for listener in list(self._listeners):
            listener()

    # ---- purifiers and sensors ----

    @callback
    def levoit_fans(self) -> dict[str, LevoitFan]:
        """Fan entity id -> purifier, for every Levoit device with a fan."""
        data = self.coordinator.data
        dev_reg = dr.async_get(self.hass)
        fans: dict[str, LevoitFan] = {}
        for device in data.devices.values() if data else ():
            if "philips" in device.components:
                continue
            controls = match_controls(
                self.hass, device.esphome_device_id, device.model, device.control_names
            )
            if (fan := controls.get("fan.fan")) is None:
                continue
            entry = dev_reg.async_get(device.esphome_device_id)
            fans[fan] = LevoitFan(
                entity_id=fan,
                name=device.name,
                title=device.title,
                model=device.model,
                device_id=device.esphome_device_id,
                area_id=entry.area_id if entry else None,
                sensors=tuple(
                    GroupSensor(controls[key], kind)
                    for key, kind in SENSOR_KEYS.items()
                    if key in controls
                ),
            )
        return fans

    @callback
    def _with_sensors(self, config: GroupConfig, fans: dict[str, LevoitFan]) -> GroupConfig:
        """The config with its members' sensors picked (minus removed ones)."""
        auto = [s for member in config.members if member in fans for s in fans[member].sensors]
        return replace(config, sensors=merge_sensors(auto, config.sensors, config.removed_sensors))

    @callback
    def group_of(self, entity_id: str) -> GroupConfig | None:
        """The group a purifier is in."""
        return next((g for g in self.groups.values() if entity_id in g.members), None)

    # ---- changes from the panel and the switch ----

    async def async_save_group(self, data: dict[str, Any]) -> GroupConfig:
        """Create or change a group; raises GroupError."""
        config = parse_config(data)
        fans = self.levoit_fans()
        if unknown := [m for m in config.members if m not in fans]:
            raise GroupError(ERR_MEMBERS, f"Not a Levoit purifier: {', '.join(unknown)}")
        if config.id and config.id not in self.groups:
            raise GroupError(ERR_NOT_FOUND, "Unknown group")
        group_id = config.id or uuid4().hex
        for other in self.groups.values():
            if other.id != group_id and (taken := set(other.members) & set(config.members)):
                raise GroupError(
                    ERR_MEMBERS, f"Already in the group {other.name}: {', '.join(sorted(taken))}"
                )
        config = self._with_sensors(replace(config, id=group_id), fans)
        await self._async_apply(config)
        return config

    async def async_set_enabled(self, group_id: str, enabled: bool) -> None:
        """Turn the group's control on or off (its switch)."""
        await self.async_change(group_id, enabled=enabled)

    async def async_change(self, group_id: str, **changes: Any) -> None:
        """Change some settings of a group (its switch and fan); raises GroupError.

        manual_level is clamped to max_speed, as in the editor.
        """
        if (config := self.groups.get(group_id)) is None:
            raise GroupError(ERR_NOT_FOUND, "Unknown group")
        changed = parse_config({**config.as_dict(), **changes}, check_members=False)
        if changed != config:
            await self._async_apply(changed)

    async def _async_apply(self, config: GroupConfig) -> None:
        old = self.groups.get(config.id)
        self.groups[config.id] = config
        if (runner := self._runners.get(config.id)) is not None:
            await runner.async_update_config(config)
        elif self._started:
            self._start_runner(config)
        await self._async_save()
        if old is None:
            async_dispatcher_send(self.hass, SIGNAL_GROUPS)
        elif old.name != config.name:
            dev_reg = dr.async_get(self.hass)
            if device := dev_reg.async_get_device_by_identifier(
                group_identifier(config.id), self.coordinator.config_entry.entry_id
            ):
                dev_reg.async_update_device(device.id, name=config.name)
        self.async_notify(config.id)

    async def async_delete_group(self, group_id: str) -> None:
        """Delete a group; the members it controls are handed back first."""
        if group_id not in self.groups:
            raise GroupError(ERR_NOT_FOUND, "Unknown group")
        if (runner := self._runners.pop(group_id, None)) is not None:
            await runner.async_release()
        del self.groups[group_id]
        self._runtime.pop(group_id, None)
        await self._async_save()
        dev_reg = dr.async_get(self.hass)
        if device := dev_reg.async_get_device_by_identifier(
            group_identifier(group_id), self.coordinator.config_entry.entry_id
        ):
            dev_reg.async_remove_device(device.id)
        self.async_notify()

    async def async_dismiss_area(self, area_id: str) -> None:
        """Hide the panel's group suggestion for this area."""
        if area_id not in self.dismissed_areas:
            self.dismissed_areas.append(area_id)
            await self._async_save()
            self.async_notify()

    # ---- state for entities and the panel ----

    @callback
    def state(self, group_id: str) -> dict[str, Any]:
        """Status, level, reason and members of a group."""
        if (runner := self._runners.get(group_id)) is not None:
            return runner.state()
        config = self.groups[group_id]
        return {
            "status": STATUS_PAUSED if not config.enabled else STATUS_WATCHING,
            "level": 0,
            "reason": None,
            "worst": None,
            "rising": None,
            "sensor_levels": {},
            "members": [
                {"entity_id": m, "speed": None, "in_control": False, "paused_until": None}
                for m in config.members
            ],
        }

    @callback
    def preview(self, data: dict[str, Any]) -> dict[str, Any]:
        """The editor's "Right now": the level an unsaved config would run at."""
        fans = self.levoit_fans()
        config = self._with_sensors(parse_config(data, check_members=False), fans)
        runner = self._runners.get(config.id)
        history = runner.keeper.history if runner else History()
        result = evaluate(config, readings := readings_of(self.hass, config), history)
        level = (
            min(config.manual_level, config.max_speed)
            if config.mode == MODE_MANUAL
            else result.target
        )
        values = {r.entity_id: r.value for r in readings}
        return {
            "level": level,
            "reason": describe(self.hass, config, result),
            "worst": result.worst.entity_id if result.worst else None,
            "rising": result.rising.entity_id if result.rising else None,
            "sensors": [
                {
                    "entity_id": s.entity_id,
                    "type": s.type,
                    "source": s.source,
                    "value": values.get(s.entity_id),
                    "level": result.levels.get(s.entity_id),
                }
                for s in config.sensors
            ],
            "members": [
                {
                    "entity_id": m,
                    "speeds": (speeds := speeds_of(self.hass, m)),
                    "speed": member_speed(level, config.max_speed, speeds),
                }
                for m in config.members
            ],
        }


def speeds_of(hass: HomeAssistant, entity_id: str) -> int:
    state = hass.states.get(entity_id)
    return speed_count(state.attributes.get(ATTR_PERCENTAGE_STEP) if state else None)


def readings_of(hass: HomeAssistant, config: GroupConfig) -> list[Reading]:
    """The group's sensors now."""
    return [
        Reading(s.entity_id, s.type, _number(hass.states.get(s.entity_id))) for s in config.sensors
    ]


def describe(hass: HomeAssistant, config: GroupConfig, result: Evaluation | None) -> str | None:
    """Why the group runs at its level: the worst (or fast rising) sensor."""
    if config.mode == MODE_MANUAL:
        return f"Manual level {min(config.manual_level, config.max_speed)}"
    if result is None:
        return None
    if not config.sensors:
        return "No air sensors"
    if result.usable == 0:
        return "No air sensor reports a value"
    reading = result.rising or result.worst
    if reading is None or reading.value is None:
        return None
    state = hass.states.get(reading.entity_id)
    name = state.name if state else reading.entity_id
    if reading.type == AQI:
        value = AQI_WORDS.get(round(reading.value), f"{reading.value:g}")
    else:
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
        value = f"{reading.value:g}{f' {unit}' if unit else ''}"
    text = f"{TYPE_LABELS[reading.type]} {value} ({name})"
    return f"{text}, rising fast" if result.rising else text


class GroupRunner:
    """One group's control loop."""

    def __init__(
        self, manager: GroupManager, config: GroupConfig, runtime: dict[str, Any] | None
    ) -> None:
        """Initialize; `runtime` is what a run before a restart left to hand back."""
        self.hass = manager.hass
        self.manager = manager
        self.config = config
        runtime = runtime or {}
        snapshots = runtime.get("snapshots")
        self.snapshots: dict[str, dict[str, Any]] = (
            dict(snapshots) if isinstance(snapshots, dict) else {}
        )
        level = runtime.get("level")
        level = min(max(level, 0), config.max_speed) if isinstance(level, int) else 0
        self.keeper = LevelKeeper(level, _now() if level else None)
        self.evaluation: Evaluation | None = None
        self.paused_until: dict[str, float] = {}
        self._targets: dict[str, int] = {}  # speed set per member
        self._no_snapshot: set[str] = set()  # came back online mid-episode
        self._own: deque[str] = deque(maxlen=64)  # context ids of our calls
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._task: asyncio.Task[None] | None = None
        self._again = False
        self._stopped = False

    def runtime(self) -> dict[str, Any]:
        """What a hand back after a restart needs."""
        return {"level": self.keeper.level, "snapshots": dict(self.snapshots)}

    @callback
    def start(self) -> None:
        """Follow the sensors and members, tick for hold and pause times."""
        self._track()
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, TICK))
        self._schedule()

    @callback
    def _track(self) -> None:
        if self._unsubs:
            self._unsubs.pop(0)()
        entities = [*self.config.members, *(s.entity_id for s in self.config.sensors)]
        self._unsubs.insert(
            0, async_track_state_change_event(self.hass, entities, self._state_changed)
        )

    @callback
    def stop(self) -> None:
        """Stop following (unload, delete)."""
        self._stopped = True
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def _tick(self, _now: datetime) -> None:
        self._schedule()

    @callback
    def _schedule(self) -> None:
        """Evaluate soon; once more after a run in progress."""
        if self._stopped:
            return
        if self._task is not None and not self._task.done():
            self._again = True
            return
        self._task = self.manager.coordinator.config_entry.async_create_background_task(
            self.hass, self._async_loop(), f"{DOMAIN} group {self.config.name}"
        )

    async def _async_loop(self) -> None:
        self._again = True
        while self._again and not self._stopped:
            self._again = False
            await self.async_evaluate()

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        if event.data["entity_id"] in self.config.members:
            self._member_changed(event)
        self._schedule()

    @callback
    def _member_changed(self, event: Event[EventStateChangedData]) -> None:
        """A person's change to a member pauses the group for it."""
        member = event.data["entity_id"]
        old, new = event.data["old_state"], event.data["new_state"]
        if new is None or new.state in OFFLINE:
            return
        if old is None or old.state in OFFLINE:
            # back online: gets the current level, without a snapshot
            if self.keeper.level > 0 and member not in self.snapshots:
                self._no_snapshot.add(member)
            return
        if (
            not self.config.respect_manual
            or member not in self._targets
            or event.context.id in self._own
            or _fan_view(old) == _fan_view(new)
        ):
            return
        if (
            new.state == STATE_ON
            and _in_manual(new)
            and _current_speed(new) == self._targets[member]
        ):
            return  # what we set, reported late
        self.paused_until[member] = _now() + self.config.manual_pause_min * 60
        self._targets.pop(member, None)
        _LOGGER.debug("%s changed by hand: group %s pauses it", member, self.config.name)
        self.manager.async_notify(self.config.id)

    async def async_update_config(self, config: GroupConfig) -> None:
        """New settings; members that left are handed back first."""
        async with self._lock:
            old = self.config
            gone = [m for m in self._controlled() if m not in config.members]
            await self._async_hand_back(gone, old.hand_back)
            for member in set(self.paused_until) - set(config.members):
                del self.paused_until[member]
            self.config = config
            if old.mode == MODE_MANUAL and config.mode == MODE_AUTO:
                self.keeper.since = None  # step down without waiting
            self.keeper.level = min(self.keeper.level, config.max_speed)
            if set(old.members) != set(config.members) or old.sensors != config.sensors:
                self._track()
        self._schedule()

    async def async_release(self) -> None:
        """Hand back every member the group controls and stop (delete)."""
        self.stop()
        async with self._lock:
            await self._async_hand_back(self._controlled(), self.config.hand_back)

    def _controlled(self) -> list[str]:
        return list(dict.fromkeys([*self.snapshots, *self._targets]))

    async def async_evaluate(self) -> None:
        """Move the level and apply it, or hand back at level 0."""
        async with self._lock:
            if self._stopped:
                return
            now = _now()
            config = self.config
            for member, until in list(self.paused_until.items()):
                if until <= now:
                    del self.paused_until[member]
            before = self.runtime()
            if not config.enabled:
                self.keeper.level = 0
                self.evaluation = None
            elif config.mode == MODE_MANUAL:
                self.keeper.manual(config)
                self.evaluation = None
            else:
                self.evaluation = self.keeper.step(config, readings_of(self.hass, config), now)
            level = self.keeper.level
            if level == 0:
                await self._async_hand_back(self._controlled(), config.hand_back)
            else:
                for member in config.members:
                    await self._async_set(member, level)
            if self.runtime() != before:
                self.manager.async_schedule_save()
        self.manager.async_notify(config.id)

    async def _async_set(self, member: str, level: int) -> None:
        """Put a member in Manual at its speed for the level."""
        if member in self.paused_until:
            return
        state = self.hass.states.get(member)
        if state is None or state.state in OFFLINE:
            return
        is_on = state.state == STATE_ON
        if not is_on and not self.config.turn_on and member not in self._targets:
            return
        if member not in self.snapshots and member not in self._no_snapshot:
            self.snapshots[member] = {
                "state": state.state,
                ATTR_PRESET_MODE: state.attributes.get(ATTR_PRESET_MODE),
                ATTR_PERCENTAGE: state.attributes.get(ATTR_PERCENTAGE),
            }
        speeds = speed_count(state.attributes.get(ATTR_PERCENTAGE_STEP))
        speed = member_speed(level, self.config.max_speed, speeds)
        self._targets[member] = speed
        if is_on and _in_manual(state) and _current_speed(state) == speed:
            return
        # a speed takes the levoit fan out of Auto / Sleep into Manual
        await self._async_call(
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: member,
                ATTR_PERCENTAGE: ranged_value_to_percentage((1, speeds), speed),
            },
        )

    async def _async_hand_back(self, members: Iterable[str], mode: str) -> None:
        """Give members back per `hand_back`; paused ones are left to the person."""
        for member in list(members):
            snapshot = self.snapshots.pop(member, None)
            self._targets.pop(member, None)
            self._no_snapshot.discard(member)
            if member in self.paused_until:
                continue
            state = self.hass.states.get(member)
            if state is None or state.state in OFFLINE:
                continue
            await self._async_hand_back_one(member, state, snapshot, mode)

    async def _async_hand_back_one(
        self, member: str, state: State, snapshot: dict[str, Any] | None, mode: str
    ) -> None:
        presets = state.attributes.get(ATTR_PRESET_MODES) or []
        speeds = speed_count(state.attributes.get(ATTR_PERCENTAGE_STEP))
        if mode == HAND_BACK_OFF:
            if state.state == STATE_ON:
                await self._async_call(SERVICE_TURN_OFF, {ATTR_ENTITY_ID: member})
            return
        if mode == HAND_BACK_LOW:
            await self._async_call(
                SERVICE_TURN_ON,
                {
                    ATTR_ENTITY_ID: member,
                    ATTR_PERCENTAGE: ranged_value_to_percentage((1, speeds), 1),
                },
            )
            return
        preset = {HAND_BACK_AUTO: PRESET_AUTO, HAND_BACK_SLEEP: PRESET_SLEEP}.get(mode)
        if preset is not None and preset in presets:
            await self._set_preset(member, state, preset)
            return
        # restore (also when the model has no such mode)
        if snapshot is None:
            return
        if snapshot.get("state") != STATE_ON:
            if state.state == STATE_ON:
                await self._async_call(SERVICE_TURN_OFF, {ATTR_ENTITY_ID: member})
            return
        before = snapshot.get(ATTR_PRESET_MODE)
        if before not in (None, PRESET_MANUAL) and before in presets:
            await self._set_preset(member, state, before)
            return
        percentage = snapshot.get(ATTR_PERCENTAGE)
        if isinstance(percentage, (int, float)) and (
            state.state != STATE_ON or state.attributes.get(ATTR_PERCENTAGE) != percentage
        ):
            await self._async_call(
                SERVICE_TURN_ON, {ATTR_ENTITY_ID: member, ATTR_PERCENTAGE: percentage}
            )

    async def _set_preset(self, member: str, state: State, preset: str) -> None:
        if state.state == STATE_ON and state.attributes.get(ATTR_PRESET_MODE) == preset:
            return
        await self._async_call(
            SERVICE_SET_PRESET_MODE, {ATTR_ENTITY_ID: member, ATTR_PRESET_MODE: preset}
        )

    async def _async_call(self, service: str, data: dict[str, Any]) -> None:
        """A fan service with our own context (so its changes are not a person's)."""
        context = Context()
        self._own.append(context.id)
        try:
            await self.hass.services.async_call(
                FAN_DOMAIN, service, data, blocking=True, context=context
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Purifier group %s: %s on %s failed: %s",
                self.config.name,
                service,
                data[ATTR_ENTITY_ID],
                err,
            )

    @callback
    def state(self) -> dict[str, Any]:
        """Status, level, reason and members, for entities and the panel."""
        config = self.config
        level = self.keeper.level
        result = self.evaluation
        if not config.enabled:
            status = STATUS_PAUSED
        elif config.mode == MODE_MANUAL:
            status = STATUS_MANUAL
        elif level > 0:
            status = STATUS_IN_CONTROL
        elif not config.sensors or (result is not None and result.usable == 0):
            status = STATUS_NO_SENSORS
        else:
            status = STATUS_WATCHING
        return {
            "status": status,
            "level": level,
            "reason": describe(self.hass, config, result) if config.enabled else None,
            "worst": result.worst.entity_id if result and result.worst else None,
            "rising": result.rising.entity_id if result and result.rising else None,
            "sensor_levels": dict(result.levels) if result else {},
            "members": [
                {
                    "entity_id": member,
                    "speed": self._targets.get(member),
                    "in_control": member in self._targets,
                    "paused_until": _iso(self.paused_until.get(member)),
                }
                for member in config.members
            ],
        }
