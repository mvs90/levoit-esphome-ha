"""Which of a device's ESPHome entities is which levoit setting, for the device page.

The device page groups a purifier's settings (Auto, Sleep, Timer, ...) instead
of listing every entity. For that it needs to know, per device, which entity is
the Auto Mode select, which the timer number, and so on.

Entities are matched by name against the device registry, so this works for
every device running the levoit component, with or without a Device Builder
config:

* the names in the device's config, when the integration has read one (they
  can be renamed there)
* otherwise the names the tuct/levoit device configs use, with a few older
  spellings and per-model exceptions

Keys are `<esphome platform>.<type>`, as in the levoit component (`fan.fan`
for the fan, which has no type).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

ESPHOME_DOMAIN = "esphome"

# Models with a device page; the others get a link to Home Assistant's device page.
SUPPORTED_MODELS = frozenset(
    {
        "CORE200S",
        "CORE300S",
        "CORE400S",
        "CORE600S",
        "LV600S",
        "VITAL100S",
        "VITAL200S",
        "EVERESTAIR",
        "ELEVA300X",
    }
)

# ESPHome platform -> Home Assistant domain (ESPHome text sensors are sensors)
PLATFORM_DOMAINS = {
    "fan": "fan",
    "select": "select",
    "number": "number",
    "switch": "switch",
    "button": "button",
    "binary_sensor": "binary_sensor",
    "sensor": "sensor",
    "text_sensor": "sensor",
}

# key -> names in the tuct/levoit device configs, current first
DEFAULT_NAMES: dict[str, tuple[str, ...]] = {
    "fan.fan": ("Fan",),
    # Auto
    "select.auto_mode": ("Auto Mode",),
    "number.auto_profile_room_size_input": ("Auto Mode Room Size Preset",),
    "number.efficiency_room_size": ("Auto Mode Room Size",),
    "sensor.efficiency_counter": ("Efficiency Counter",),
    "text_sensor.auto_mode_room_size_high_fan": ("Auto: High remaining run time",),
    "switch.adaptive_start": ("Adaptive Start",),
    "switch.dynamic_manual": ("Dynamic Manual",),
    "select.fan_operating_mode": ("Fan Operating Mode",),
    # Sleep / quiet (Vital 200S, Eleva 300X)
    "select.sleep_preference": ("Sleep Mode Type", "Sleep Preference"),
    "number.sleep_minutes": ("Sleep Mode Minutes",),
    "number.sleep_fan_level": ("Sleep Fan Level (5=auto)", "Sleep Fan Level"),
    "switch.quick_clean": ("Quick Clean Preset", "Quick Clean"),
    "number.quick_clean_minutes": ("Quick Clean Minutes",),
    "number.quick_clean_fan_level": ("Quick Clean Fan Level",),
    "switch.daytime_enabled": ("Daytime Preset", "Daytime Enabled"),
    "select.daytime_fan_mode": ("Daytime Fan Mode",),
    "number.daytime_fan_level": ("Daytime Fan Level",),
    "switch.quiet_period": ("Quiet Period",),
    "select.quiet_trigger": ("Quiet Trigger",),
    "number.quiet_start": ("Quiet Start",),
    "number.quiet_end": ("Quiet End",),
    "binary_sensor.quiet_active": ("Quiet Active",),
    "switch.dynamic_sleep": ("Dynamic Sleep",),
    # Timer
    "number.timer": ("Timer (min)", "Timer"),
    "text_sensor.timer_duration_initial": ("Timer Duration", "Timer Set"),
    "text_sensor.timer_duration_remaining": ("Timer Remaining",),
    # Display and panel
    "switch.display": ("Display",),
    "switch.child_lock": ("Child Lock",),
    "switch.light_detect": ("Light Detect",),
    "binary_sensor.dark_detected": ("Dark Detected",),
    "select.nightlight": ("Night Light", "Nightlight"),
    "switch.mute": ("Mute",),
    "switch.aqi_ring_dim": ("AQI Ring Dim",),
    "number.vent_angle": ("Vent Angle",),
    # Air quality
    "sensor.pm25": ("PM 2.5", "AQ - PM 2.5", "PM2.5"),
    "sensor.pm1_0": ("PM 1.0", "PM1.0"),
    "sensor.pm10": ("PM 10", "PM10"),
    "sensor.aqi": ("AQI",),
    "sensor.aqi_index": (),  # Eleva only, see MODEL_NAMES
    "sensor.ambient_light": ("Ambient Light",),
    # Filter
    "sensor.filter_life_left": ("Filter %", "Filter Life Left", "Filter Life %"),
    "binary_sensor.filter_low": ("Filter Low",),
    "number.filter_lifetime_months": ("Filter Months", "Filter Lifetime", "Filter Lifetime Months"),
    "button.reset_filter_stats": ("Filter Reset", "Reset Filter Stats"),
    "sensor.current_cadr": ("Current CADR",),
    # Info
    "binary_sensor.cover_open": ("Cover Open",),
    "text_sensor.error_message": ("Error",),
    "text_sensor.mcu_version": ("MCU Version",),
    "text_sensor.esp_version": ("ESP Version",),
    "text_sensor.model": ("Model",),
}

# Where a model names an entity differently; tried before DEFAULT_NAMES.
MODEL_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "LV600S": {
        "switch.power": ("Power", "Ein"),
        "select.humidifier_mode": ("Operating Mode", "Betriebsmodus"),
        "number.humidity_target": ("Target Humidity", "Zielfeuchte"),
        "number.mist_level": ("Mist Level", "Nebelstufe"),
        "number.timer": ("Timer (min)", "Timer Minuten"),
        "number.warm_level": ("Warm Level", "Warmnebelstufe"),
        "sensor.humidity": ("Humidity", "Luftfeuchtigkeit"),
        "sensor.temperature": ("Temperature", "Temperatur"),
        "sensor.timer_remaining_seconds": ("Timer Remaining Seconds", "Timer Restzeit"),
        "binary_sensor.water_tank_empty": ("Water Tank Empty", "Wassermangel"),
        "binary_sensor.tank_removed": ("Tank Removed", "Tank entfernt"),
        "binary_sensor.humidifying": ("Humidifying", "Befeuchtet"),
        "binary_sensor.heating_enabled": ("Heating Enabled", "Waerme aktiv"),
        "binary_sensor.mcu_connection": ("MCU Connection", "MCU Verbindung"),
        "binary_sensor.mcu_fault": ("MCU Fault", "Geraetefehler"),
        "text_sensor.error_message": ("Error", "Fehlermeldung"),
    },
    # The Eleva's "AQI" is the 0-500 index; its 1-4 level is "Air Quality Level".
    "ELEVA300X": {
        "sensor.aqi_index": ("AQI",),
        "sensor.aqi": ("Air Quality Level",),
    },
}


def page_supported(
    model: str | None, components: Iterable[str], controls: Mapping[str, str]
) -> bool:
    """Whether the device page has sections for this device.

    A known model decides; a device that does not report its model counts when
    it runs the levoit component and has its fan entity.
    """
    if model is not None:
        return model in SUPPORTED_MODELS
    return "philips" not in components and "fan.fan" in controls


def config_names(config: Mapping[str, Any]) -> dict[str, str]:
    """Entity names per key, from the resolved purifier or LV600S config.

    Only the names are kept: the config itself has secrets.
    """
    names: dict[str, str] = {}
    for platform in PLATFORM_DOMAINS:
        entries = config.get(platform)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("platform") != "levoit":
                continue
            kind = "fan" if platform == "fan" else entry.get("type")
            name = entry.get("name")
            if isinstance(kind, str) and isinstance(name, str) and name:
                names[f"{platform}.{kind}"] = name
    # The LV600S component declares sensors within its parent block; controls
    # are template entities. Read only explicit names/IDs, never execute lambdas.
    lv = config.get("lv600s_humidifier")
    if isinstance(lv, dict):
        nested = {
            "current_humidity": "sensor.humidity",
            "current_temperature": "sensor.temperature",
            "timer_remaining": "sensor.timer_remaining_seconds",
            "water_lacks": "binary_sensor.water_tank_empty",
            "tank_removed": "binary_sensor.tank_removed",
            "humidifying": "binary_sensor.humidifying",
            "warm_enabled": "binary_sensor.heating_enabled",
            "online": "binary_sensor.mcu_connection",
            "fault": "binary_sensor.mcu_fault",
            "fault_message": "text_sensor.error_message",
            "mcu_version": "text_sensor.mcu_version",
            "esp_version": "text_sensor.esp_version",
            "model_sensor": "text_sensor.model",
        }
        for key, kind in nested.items():
            entry = lv.get(key)
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                names[kind] = entry["name"]
        ids = {
            "humidifier_power": "switch.power",
            "humidifier_display": "switch.display",
            "humidifier_mode": "select.humidifier_mode",
            "humidifier_target": "number.humidity_target",
            "humidifier_mist": "number.mist_level",
            "humidifier_warm": "number.warm_level",
            "humidifier_timer": "number.timer",
        }
        for platform in ("switch", "select", "number"):
            for entry in config.get(platform) or []:
                if (
                    isinstance(entry, dict)
                    and entry.get("platform") == "template"
                    and entry.get("id") in ids
                    and isinstance(entry.get("name"), str)
                ):
                    names[ids[entry["id"]]] = entry["name"]
    return names


def _norm(name: str) -> str:
    return " ".join(name.casefold().split())


def _candidates(key: str, model: str | None, configured: Mapping[str, str]) -> Iterable[str]:
    if key in configured:
        yield configured[key]
    yield from MODEL_NAMES.get(model or "", {}).get(key, ())
    if key not in MODEL_NAMES.get(model or "", {}):
        yield from DEFAULT_NAMES.get(key, ())


def match_controls(
    hass: HomeAssistant,
    device_id: str,
    model: str | None,
    configured: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Key -> entity_id for the device's ESPHome entities that are known settings.

    An entity is used once. Names from the config win over the defaults, and a
    model's own names over the shared ones, so the Eleva's "AQI" is its index,
    not the level.
    """
    configured = configured or {}
    entities: list[tuple[str, str, str]] = []  # domain, normalised name, entity_id
    for entry in er.async_entries_for_device(er.async_get(hass), device_id):
        if entry.platform != ESPHOME_DOMAIN or entry.disabled_by is not None:
            continue
        if entry.original_name:
            entities.append((entry.domain, _norm(entry.original_name), entry.entity_id))

    # keys with a specific source first: config names, then model exceptions
    model_names = MODEL_NAMES.get(model or "", {})
    available_keys = dict.fromkeys((*DEFAULT_NAMES, *model_names))
    if model == "LV600S":
        # An auxiliary fan on this ESPHome node is not a purifier group member.
        del available_keys["fan.fan"]
    keys = sorted(
        available_keys,
        key=lambda k: (k not in configured, k not in model_names),
    )
    found: dict[str, str] = {}
    used: set[str] = set()

    def match(key: str, *, suffix: bool) -> None:
        domain = PLATFORM_DOMAINS[key.split(".", 1)[0]]
        for name in _candidates(key, model, configured):
            wanted = _norm(name)
            for entity_domain, entity_name, entity_id in entities:
                if entity_domain != domain or entity_id in used:
                    continue
                # suffix: older configs without friendly_name put the device
                # name in front ("bedroom Auto Mode")
                if entity_name == wanted or (suffix and entity_name.endswith(f" {wanted}")):
                    found[key] = entity_id
                    used.add(entity_id)
                    return

    for key in keys:
        match(key, suffix=False)
    for key in keys:
        if key not in found:
            match(key, suffix=True)
    return found
