"""Add device: what the config flow and the panel's wizard share.

Add device makes a Device Builder config from a template of tuct/levoit
(devices/templates.json: a model, original ESP, ESP32-C3 or Seeed XIAO ESP32-S3):

* new device: suggested name, a generated API encryption key stored in
  secrets.yaml as <name>_api_key, OTA encrypted with it (a generated OTA
  password, <name>_ota_password, only on a Device Builder too old for that)
* existing device (in Home Assistant, but no Device Builder config): its name,
  its API key from the ESPHome config entry, its OTA password as entered

Either way the ESP is a template (the config follows it: every update rewrites
it from the newest builder file) or custom: the model's builder file with the
user's own board and UART pins, never rewritten.

Wi-Fi comes from the shared wifi_ssid / wifi_password / wifi_ap_password
secrets, which must exist. Only secret names are read, never values; a secret
that exists is never overwritten.

The config flow (config_flow.py) and the WebSocket commands of the panel
(onboarding_websocket.py) are forms over the functions here: the choices,
the protection rule, and the one step that writes anything,
`async_create_device`. Plain data in and out, so the rule is tested once.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import templates as tpl
from .const import CHANNEL_MAIN, CHANNEL_STABLE
from .device_builder import (
    DeviceBuilder,
    DeviceBuilderCommandError,
    async_add_secret,
    async_create_config,
    async_secret_names,
    builder_page_url,
)

if TYPE_CHECKING:
    from .coordinator import LevoitDevice, LevoitEsphomeCoordinator

WIFI_SECRETS = ("wifi_ssid", "wifi_password", "wifi_ap_password")
# offered for a custom config; any other ESPHome board name can be typed in
COMMON_BOARDS = (
    "seeed_xiao_esp32s3",
    "seeed_xiao_esp32c3",
    "seeed_xiao_esp32c6",
    "esp32dev",
    "esp32-s3-devkitc-1",
    "esp32-c3-devkitm-1",
    "esp32-c6-devkitc-1",
)
CHANNELS = (CHANNEL_STABLE, CHANNEL_MAIN)
ESPHOME_DOMAIN = "esphome"
SUBENTRY_TYPE = "device"
INTEGRATION_PAGE = "/config/integrations/integration/esphome"

# The error texts of translations/en.json (config_subentries.device.error and
# .abort), for the panel, which has no translations.
MESSAGES = {
    "invalid_name": "Use lowercase letters, digits and hyphens, at most 31 characters.",
    "invalid_board": (
        "Use an ESPHome board name: lowercase letters, digits, hyphens, underscores and dots."
    ),
    "invalid_pin": "Enter a GPIO number, e.g. GPIO5.",
    "same_pin": "RX and TX must be different pins.",
    "name_taken": "A device or config with this name exists already.",
    "missing_wifi_secrets": (
        "The Device Builder's secrets.yaml has no {missing}. Add them there "
        "(Secrets in the Device Builder), then try again."
    ),
    "secret_exists": "secrets.yaml already has {secret}. Remove it there or pick another name.",
    "config_exists": "The Device Builder already has a config with this name.",
    "template_failed": (
        "The template could not be read from GitHub or does not have the expected shape."
    ),
    "cannot_connect": "The ESPHome Device Builder did not answer.",
    "no_device_builder": "The ESPHome Device Builder add-on is not available.",
    "templates_unavailable": "The device templates could not be read from GitHub.",
    "unknown_template": "There is no such template.",
    "unknown_device": "Home Assistant has no such device without a config.",
    "invalid_channel": "The channel is stable or main.",
}


class _Placeholders(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


class OnboardingError(Exception):
    """Add device cannot go on; `code` is an error key of the config flow's translations."""

    def __init__(self, code: str, **placeholders: str) -> None:
        """Initialize."""
        self.code = code
        self.placeholders = placeholders
        super().__init__(MESSAGES.get(code, code).format_map(_Placeholders(placeholders)))

    @property
    def message(self) -> str:
        """The text, with its placeholders filled in."""
        return str(self)


# --- the choices ----------------------------------------------------------------


def models(templates: Iterable[tpl.Template]) -> list[tuple[str, str]]:
    """The models with a template, (model, title), by title."""
    found: dict[str, str] = {}
    for template in templates:
        found.setdefault(template.model, template.title)
    return sorted(found.items(), key=lambda item: item[1])


def variants(templates: Iterable[tpl.Template], model: str) -> list[tpl.Template]:
    """The templates of a model, in the order of templates.json."""
    return [t for t in templates if t.model == model]


def custom_base(model_variants: list[tpl.Template]) -> tpl.Template:
    """The template a custom config of the model starts from: closest to a bare ESP."""
    return next(
        (t for v in tpl.CUSTOM_BASE for t in model_variants if t.variant == v), model_variants[0]
    )


def unconfigured(coordinator: LevoitEsphomeCoordinator) -> list[LevoitDevice]:
    """The devices Home Assistant knows that have no Device Builder config."""
    data = coordinator.data
    return [d for d in data.devices.values() if not d.configuration] if data else []


@callback
def existing_api_key(hass: HomeAssistant, name: str) -> str | None:
    """The API encryption key Home Assistant uses for the device, if any."""
    for entry in hass.config_entries.async_entries(ESPHOME_DOMAIN):
        if entry.data.get("device_name") == name:
            return entry.data.get("noise_psk") or None
    return None


def validate_custom(board: str, rx_pin: str, tx_pin: str) -> tuple[tpl.CustomEsp | None, dict]:
    """The user's own ESP, normalised; or the errors per field (board, rx_pin, tx_pin)."""
    errors: dict[str, str] = {}
    board = board.strip().lower()
    rx = tpl.normalize_pin(rx_pin)
    tx = tpl.normalize_pin(tx_pin)
    if not tpl.valid_board(board):
        errors["board"] = "invalid_board"
    if rx is None:
        errors["rx_pin"] = "invalid_pin"
    if tx is None:
        errors["tx_pin"] = "invalid_pin"
    elif rx == tx:
        errors["tx_pin"] = "same_pin"
    if errors:
        return None, errors
    assert rx is not None and tx is not None
    return tpl.CustomEsp(board=board, rx_pin=rx, tx_pin=tx), {}


def check_name(name: str, taken: Iterable[str]) -> str | None:
    """Why a name for a new device cannot be used (invalid_name, name_taken), or None."""
    if not tpl.valid_name(name):
        return "invalid_name"
    if name in taken:
        return "name_taken"
    return None


@dataclass(frozen=True)
class BuilderState:
    """What the Device Builder's listing says that Add device needs."""

    taken: frozenset[str]  # names in use: its configs, Home Assistant's devices, our entries
    esphome_version: str | None  # the ESPHome it runs, from any device; None if it cannot tell


async def async_builder_state(
    hass: HomeAssistant, builder: DeviceBuilder, coordinator: LevoitEsphomeCoordinator
) -> BuilderState:
    """Read the Device Builder's listing; cannot_connect if it does not answer."""
    try:
        listing = await builder.api.get_devices()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise OnboardingError("cannot_connect") from err
    configured = [d for d in listing.get("configured", []) if d.get("name")]
    taken = {d["name"] for d in configured}
    taken |= set(coordinator.data.devices) if coordinator.data else set()
    taken |= {
        sub.unique_id
        for sub in coordinator.config_entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE and sub.unique_id
    }
    version = next((d["current_version"] for d in configured if d.get("current_version")), None)
    return BuilderState(taken=frozenset(taken), esphome_version=version)


# --- protection ----------------------------------------------------------------------


@dataclass(frozen=True)
class Protection:
    """What a new config is protected with, and the secrets that get written for it."""

    values: tpl.ConfigValues
    secrets: dict[str, str]  # secrets.yaml entries to add: name -> value

    @property
    def encrypted_ota(self) -> bool:
        """OTA encrypted with the API key (else a password, or nothing)."""
        return self.values.ota_uses_api_key


def protection(
    name: str,
    channel: str,
    *,
    existing: bool,
    api_key: str | None = None,
    ota_password: str | None = None,
    esphome_version: str | None = None,
) -> Protection:
    """The protection rule.

    New device: a new API key, OTA encrypted with it; an OTA password instead
    on a Device Builder before ESPHome 2026.9.0. Existing device: the key Home
    Assistant has (none: no encryption) and the OTA password as given (none:
    no OTA protection), so its first update installs whatever its firmware
    accepts; after that upload the coordinator switches a config with a key to
    encrypted OTA, as it does for a password.
    """
    api_secret = tpl.secret_key(name, "api_key")
    ota_secret = tpl.secret_key(name, "ota_password")
    secrets: dict[str, str] = {}
    if not existing:
        api_key = tpl.new_api_key()
        if not tpl.supports_ota_encryption(esphome_version):
            ota_password = tpl.new_ota_password()
    if api_key:
        secrets[api_secret] = api_key
    if ota_password:
        secrets[ota_secret] = ota_password
    values = tpl.ConfigValues(
        name=name,
        api_key=tpl.Value(secret=api_secret) if api_key else None,
        ota_password=tpl.Value(secret=ota_secret) if ota_password else None,
        channel=channel,
        ota_uses_api_key=not existing and bool(api_key) and not ota_password,
    )
    return Protection(values=values, secrets=secrets)


# --- creating the config ---------------------------------------------------------------


@dataclass(frozen=True)
class DeviceRequest:
    """What Add device was told."""

    template: tpl.Template
    name: str
    channel: str
    existing: bool = False  # a device already in Home Assistant: keeps name and key
    custom: tpl.CustomEsp | None = None  # Other ESP: own board and pins, a custom config
    ota_password: str | None = None  # an existing device's, if it has one
    source: str | None = None  # the template's builder file, when fetched already


@dataclass(frozen=True)
class CreatedDevice:
    """The config Add device made."""

    name: str
    configuration: str
    template: str
    existing: bool
    custom: bool
    encrypted_ota: bool
    builder_url: str

    @property
    def subentry_data(self) -> dict[str, Any]:
        """The data of the device's sub-entry under the integration's entry."""
        return {
            "configuration": self.configuration,
            "template": self.template,
            "existing": self.existing,
            "custom": self.custom,
        }


def render(request: DeviceRequest, source: str, values: tpl.ConfigValues) -> str:
    """The new config: a template config, or a custom one for the user's ESP."""
    if request.custom is not None:
        return tpl.render_custom(source, request.template, values, request.custom)
    return tpl.render(source, request.template, values)


async def async_create_device(
    hass: HomeAssistant,
    coordinator: LevoitEsphomeCoordinator,
    builder: DeviceBuilder,
    request: DeviceRequest,
    esphome_version: str | None,
) -> CreatedDevice:
    """Secrets, then the config, in the Device Builder; OnboardingError if it did not work.

    The name must have been checked (`check_name`) first. Nothing is written
    until the Wi-Fi secrets are there and none of the new secrets exists.
    """
    if request.channel not in CHANNELS:
        raise OnboardingError("invalid_channel")
    name = request.name
    chosen = protection(
        name,
        request.channel,
        existing=request.existing,
        api_key=existing_api_key(hass, name) if request.existing else None,
        ota_password=request.ota_password,
        esphome_version=esphome_version,
    )
    try:
        present = await async_secret_names(hass, builder)
        if missing := [key for key in WIFI_SECRETS if key not in present]:
            raise OnboardingError("missing_wifi_secrets", missing=", ".join(missing))
        if exists := [key for key in chosen.secrets if key in present]:
            raise OnboardingError("secret_exists", secret=", ".join(exists))

        source = request.source or await tpl.async_fetch_template_text(
            async_get_clientsession(hass), request.template
        )
        content = render(request, source, chosen.values)

        for key, value in chosen.secrets.items():
            if not await async_add_secret(hass, builder, key, value):
                raise OnboardingError("secret_exists", secret=key)
        configuration = await async_create_config(hass, builder, name, content)
    except DeviceBuilderCommandError as err:
        code = "config_exists" if err.code == "already_exists" else "cannot_connect"
        raise OnboardingError(code) from err
    except (aiohttp.ClientError, TimeoutError, tpl.TemplateError) as err:
        raise OnboardingError("template_failed") from err

    await coordinator.async_request_refresh()
    return CreatedDevice(
        name=name,
        configuration=configuration,
        template=request.template.file,
        existing=request.existing,
        custom=request.custom is not None,
        encrypted_ota=chosen.encrypted_ota,
        builder_url=builder_page_url(builder) or INTEGRATION_PAGE,
    )


@callback
def async_add_subentry(hass: HomeAssistant, entry: ConfigEntry, created: CreatedDevice) -> bool:
    """The device's sub-entry, as the config flow's create_entry makes it.

    Adding it sets the entry up again (its update listener), which lists the
    config as pending until the device connects. False if one exists already.
    """
    subentry = ConfigSubentry(
        data=MappingProxyType(created.subentry_data),
        subentry_type=SUBENTRY_TYPE,
        title=created.name,
        unique_id=created.name,
    )
    try:
        return hass.config_entries.async_add_subentry(entry, subentry)
    except AbortFlow:
        return False
