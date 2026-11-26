"""Expose an LV600S as a Home Assistant humidifier backed by ESPHome."""

from __future__ import annotations

import asyncio
from math import isfinite
from typing import TYPE_CHECKING, Any

from homeassistant.components.humidifier import (
    MODE_AUTO,
    MODE_SLEEP,
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .controls import match_controls
from .entity import LevoitEsphomeEntity, async_add_per_device

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import LevoitEsphomeConfigEntry
    from .coordinator import LevoitEsphomeCoordinator

PARALLEL_UPDATES = 0

_POWER = "switch.power"
_MODE = "select.humidifier_mode"
_MODE_STATUS = "text_sensor.humidifier_mode_status"
_TARGET = "number.humidity_target"
_CONNECTION = "binary_sensor.mcu_connection"
_HUMIDIFYING = "binary_sensor.humidifying"
_HUMIDITY = "sensor.humidity"
_SAFETY = (
    "binary_sensor.water_tank_empty",
    "binary_sensor.tank_removed",
    "binary_sensor.mcu_fault",
)
_SOURCES = (_POWER, _MODE, _MODE_STATUS, _TARGET, _CONNECTION, _HUMIDIFYING, _HUMIDITY, *_SAFETY)
_MODES = {
    "manual": ("Manual", "Manuell"),
    MODE_AUTO: ("Auto", "Auto (Feuchte)", "Humidity", "Feuchte"),
    MODE_SLEEP: ("Humidity Sleep", "Schlaf"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LevoitEsphomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a humidifier entity for each LV600S."""
    entry.async_on_unload(
        async_add_per_device(
            entry.runtime_data,
            async_add_entities,
            lambda coordinator, name: (
                [LV600SHumidifier(coordinator, name)]
                if coordinator.data.devices[name].model == "LV600S"
                else []
            ),
        )
    )


class LV600SHumidifier(LevoitEsphomeEntity, HumidifierEntity):
    """Forward requests to the actual LV600S controls and track their feedback."""

    _attr_name = None
    _attr_translation_key = "lv600s"
    _attr_device_class = HumidifierDeviceClass.HUMIDIFIER
    _attr_min_humidity = 40
    _attr_max_humidity = 80
    _attr_target_humidity_step = 1

    def __init__(self, coordinator: LevoitEsphomeCoordinator, name: str) -> None:
        """Set up state subscriptions and serialize appliance actions."""
        super().__init__(coordinator, name, "humidifier")
        self._sources: dict[str, str] = {}
        self._unsub_sources: CALLBACK_TYPE | None = None
        self._commands = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        """Follow the ESPHome entities without polling the Device Builder."""
        await super().async_added_to_hass()
        self._follow_sources()
        self.async_on_remove(self._stop_following)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._follow_sources()
        super()._handle_coordinator_update()

    @callback
    def _follow_sources(self) -> None:
        device = self.device
        controls = (
            match_controls(self.hass, device.esphome_device_id, device.model, device.control_names)
            if device is not None
            else {}
        )
        sources = {key: controls[key] for key in _SOURCES if key in controls}
        if sources == self._sources:
            return
        self._stop_following()
        self._sources = sources
        if sources:
            self._unsub_sources = async_track_state_change_event(
                self.hass, tuple(sources.values()), self._source_changed
            )

    @callback
    def _source_changed(self, _event: object) -> None:
        self.async_write_ha_state()

    @callback
    def _stop_following(self) -> None:
        if self._unsub_sources:
            self._unsub_sources()
            self._unsub_sources = None

    def _state(self, key: str) -> State | None:
        entity_id = self._sources.get(key)
        return self.hass.states.get(entity_id) if entity_id else None

    def _value(self, key: str) -> str | None:
        state = self._state(key)
        return state.state if state is not None else None

    def _number(self, key: str) -> float | None:
        try:
            value = float(self._value(key) or "")
        except ValueError:
            return None
        return value if isfinite(value) else None

    @property
    def available(self) -> bool:
        """Require a usable power state and current MCU connection when mapped."""
        return (
            super().available
            and self.is_on is not None
            and (_CONNECTION not in self._sources or self._value(_CONNECTION) == STATE_ON)
        )

    @property
    def is_on(self) -> bool | None:
        value = self._value(_POWER)
        return value == STATE_ON if value in (STATE_ON, STATE_OFF) else None

    @property
    def action(self) -> HumidifierAction | None:
        value = self._value(_HUMIDIFYING)
        if value == STATE_ON:
            return HumidifierAction.HUMIDIFYING
        return HumidifierAction.IDLE if value == STATE_OFF else None

    @property
    def current_humidity(self) -> float | None:
        return self._number(_HUMIDITY)

    @property
    def target_humidity(self) -> float | None:
        return self._number(_TARGET)

    def _mode_options(self) -> dict[str, str]:
        state = self._state(_MODE)
        options = state.attributes.get("options", ()) if state is not None else ()
        return {
            mode: option
            for mode, aliases in _MODES.items()
            if (option := next((alias for alias in aliases if alias in options), None))
        }

    @property
    def supported_features(self) -> HumidifierEntityFeature:
        return HumidifierEntityFeature.MODES if self._mode_options() else HumidifierEntityFeature(0)

    @property
    def available_modes(self) -> list[str]:
        return list(self._mode_options())

    @property
    def _mode_source(self) -> str:
        return _MODE_STATUS if self._state(_MODE_STATUS) is not None else _MODE

    @property
    def mode(self) -> str | None:
        raw = self._value(self._mode_source)
        return next((mode for mode, aliases in _MODES.items() if raw in aliases), None)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        raw = self._value(self._mode_source)
        if raw in ("Auto (read only)", "Auto (Original)"):
            return {"reported_mode": "original_auto"}
        return {"reported_mode": "unknown"} if self.mode is None else {}

    def _require_safe(self) -> None:
        if not self.available or any(
            key in self._sources and self._value(key) != STATE_OFF for key in _SAFETY
        ):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="lv600s_unready")

    async def _call(self, key: str, service: str, **data: Any) -> None:
        entity_id = self._sources.get(key)
        if entity_id is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="lv600s_unready")
        await self.hass.services.async_call(
            key.split(".", 1)[0],
            service,
            {"entity_id": entity_id, **data},
            blocking=True,
            context=self._context,
        )

    async def _wait_for(self, key: str, value: str) -> None:
        try:
            async with asyncio.timeout(8):
                while self._value(key) != value:
                    self._require_safe()
                    await asyncio.sleep(0.15)
        except TimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="lv600s_no_confirmation"
            ) from err
        self._require_safe()

    async def _ensure_power(self) -> None:
        self._require_safe()
        if not self.is_on:
            await self._call(_POWER, "turn_on")
            await self._wait_for(_POWER, STATE_ON)

    async def _set_mode(self, mode: str) -> None:
        option = self._mode_options().get(mode)
        if option is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="lv600s_unready")
        await self._ensure_power()
        if self._value(self._mode_source) != option:
            await self._call(_MODE, "select_option", option=option)
            await self._wait_for(self._mode_source, option)

    async def async_turn_on(self, **kwargs: Any) -> None:
        async with self._commands:
            await self._ensure_power()

    async def async_turn_off(self, **kwargs: Any) -> None:
        async with self._commands:
            await self._call(_POWER, "turn_off")

    async def async_set_mode(self, mode: str) -> None:
        async with self._commands:
            await self._set_mode(mode)

    async def async_set_humidity(self, humidity: int) -> None:
        async with self._commands:
            if _TARGET not in self._sources:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="lv600s_unready"
                )
            await self._set_mode(MODE_AUTO)
            await self._call(_TARGET, "set_value", value=humidity)
