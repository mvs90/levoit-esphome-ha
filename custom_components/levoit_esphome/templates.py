"""Device templates: the builder files of tuct/levoit.

A config made from a template keeps a marker line naming it:

    # levoit-esphome-ha: template=devices/levoit-everest-air/levoit-everest-air-builder-c3.yaml

Builder files pasted by hand are recognised by their generated header
("# Generated from devices/<source> by devices/make-builder-yaml.ps1").
A config with neither is custom: it is never rewritten.

Rendering takes the newest builder file and puts the device's own values in:
its name, API and OTA credentials, and channel. Parse the old YAML structurally
without resolving secrets, then edit the generated template as text so its
comments and layout stay.
Plain Python without Home Assistant, so it is easy to test.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import re
import secrets as pysecrets

import aiohttp
import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from .const import CHANNEL_MAIN, CHANNEL_STABLE, GITHUB_RAW, GITHUB_REPO

TEMPLATES_FILE = "devices/templates.json"
# Templates come from main: the newest builder files. The component itself comes
# from the device's channel (`ref:`); device configs only use released options.
TEMPLATES_REF = "main"

VARIANT_ORIGINAL = "original"
VARIANT_XIAO_C3 = "xiao_c3"
VARIANT_C3 = "c3"
VARIANT_S3 = "s3"
VARIANT_CUSTOM = "custom"
# the ESP variants this version knows; templates with others are skipped
VARIANTS = (VARIANT_ORIGINAL, VARIANT_XIAO_C3, VARIANT_C3, VARIANT_S3)
VARIANT_TITLES = {
    VARIANT_ORIGINAL: "original ESP",
    VARIANT_XIAO_C3: "Seeed XIAO ESP32-C3",
    VARIANT_C3: "ESP32-C3",
    VARIANT_S3: "Seeed XIAO ESP32-S3",
}
# Which template a custom config starts from, best first
CUSTOM_BASE = (VARIANT_XIAO_C3, VARIANT_C3, VARIANT_S3, VARIANT_ORIGINAL)
DEVICES_URL = "https://github.com/tuct/levoit/tree/main/devices/"

MARKER_PREFIX = "# levoit-esphome-ha: template="
_MARKER = re.compile(r"(?m)^# levoit-esphome-ha: template=(\S+)[ \t]*$")
_GENERATED = re.compile(
    r"(?m)^# Generated from (devices/\S+\.yaml) by devices/make-builder-yaml\.ps1"
)
_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,29}[a-z0-9])?$")
_BOARD = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_PIN = re.compile(r"^(?:gpio)?0*(\d{1,2})$", re.IGNORECASE)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


@dataclass(frozen=True)
class Template:
    """One entry of devices/templates.json."""

    title: str
    model: str
    variant: str
    board: str
    name: str
    file: str
    source: str


@dataclass(frozen=True)
class Value:
    """How a config sets a value: by `!secret <name>`, inline, or not at all."""

    secret: str | None = None
    inline: str | None = None

    @property
    def yaml(self) -> str:
        """The value as written in the config."""
        if self.secret is not None:
            return f"!secret {self.secret}"
        return json.dumps(self.inline or "", ensure_ascii=False)


@dataclass(frozen=True)
class ConfigValues:
    """What a device keeps when its config is (re)made from a template."""

    name: str
    api_key: Value | None = None  # None: no API encryption
    ota_password: Value | None = None  # None: no OTA password
    channel: str | None = None  # None: as in the template (stable)
    ota_encryption_key: Value | None = None  # required encrypted native OTA
    ota_uses_api_key: bool = False  # bare OTA encryption inherits the API key


@dataclass(frozen=True)
class CustomEsp:
    """The user's own ESP for a custom config: ESPHome board name and UART pins."""

    board: str
    rx_pin: str
    tx_pin: str


class TemplateError(ValueError):
    """A builder file does not have the shape rendering expects."""


# --- GitHub -----------------------------------------------------------------


async def async_fetch_templates(session: aiohttp.ClientSession) -> list[Template]:
    """devices/templates.json of tuct/levoit (main)."""
    url = f"{GITHUB_RAW}/{TEMPLATES_REF}/{TEMPLATES_FILE}"
    async with session.get(url, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    return parse_templates(data)


def parse_templates(data: dict) -> list[Template]:
    """The templates of templates.json this version can offer.

    A variant added to tuct/levoit later (a new ESP) is skipped until the
    integration knows it, instead of reaching the config type sensor, whose
    states are a fixed list.
    """
    return [
        Template(**entry) for entry in data.get("templates", []) if entry.get("variant") in VARIANTS
    ]


async def async_fetch_template_text(session: aiohttp.ClientSession, template: Template) -> str:
    """The builder file of a template (main)."""
    url = f"{GITHUB_RAW}/{TEMPLATES_REF}/{template.file}"
    async with session.get(url, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        return (await resp.text()).replace("\r\n", "\n")


# --- recognising and reading configs ------------------------------------------


def template_of(config_text: str, templates: list[Template]) -> Template | None:
    """The template a config was made from; None for a custom config."""
    if match := _MARKER.search(config_text):
        return next((t for t in templates if t.file == match.group(1)), None)
    if match := _GENERATED.search(config_text):
        return next((t for t in templates if t.source == match.group(1)), None)
    return None


def _mapping(node: Node | None, label: str) -> dict[str, Node]:
    """Inspect YAML structure without expanding ESPHome tags, includes or secrets."""
    error = TemplateError(f"unsupported {label} configuration; use a custom config")
    if not isinstance(node, MappingNode) or node.tag != "tag:yaml.org,2002:map":
        raise error
    fields: dict[str, Node] = {}
    for key, value in node.value:
        if (
            not isinstance(key, ScalarNode)
            or key.tag != "tag:yaml.org,2002:str"
            or key.value in fields
        ):
            raise error
        fields[key.value] = value
    return fields


def _credential(node: Node | None, label: str) -> Value:
    if isinstance(node, ScalarNode) and node.value:
        if node.tag == "!secret" and re.fullmatch(r"[A-Za-z0-9_.-]+", node.value):
            return Value(secret=node.value)
        if node.tag == "tag:yaml.org,2002:str" and not re.search(r"\$\{|[\r\n]", node.value):
            return Value(inline=node.value)
    raise TemplateError(f"unsupported {label} credential; use a custom config")


def _template_fields(config_text: str) -> dict[str, Node]:
    try:
        fields = _mapping(yaml.compose(config_text, Loader=yaml.SafeLoader), "template")
    except yaml.YAMLError:
        # Parser details can contain inline credentials.
        raise TemplateError("invalid template YAML; use a custom config") from None
    if "packages" in fields:
        raise TemplateError("templates with packages must be managed as custom configs")
    return fields


def _string(node: Node | None) -> str | None:
    if isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:str":
        return node.value
    return None


def _template_channel(fields: dict[str, Node]) -> str:
    """The renderer can update only the upstream main/stable builder source."""
    external = fields.get("external_components")
    if not isinstance(external, SequenceNode) or len(external.value) != 1:
        raise TemplateError("unsupported component sources; use a custom config")
    entry = _mapping(external.value[0], "external component")
    source = _mapping(entry.get("source"), "component source")
    url = _string(source.get("url")) or ""
    ref = _string(source.get("ref")) if "ref" in source else CHANNEL_MAIN
    if (
        _string(source.get("type")) != "git"
        or url.removesuffix(".git") != f"https://github.com/{GITHUB_REPO}"
        or ref not in (CHANNEL_MAIN, CHANNEL_STABLE)
    ):
        raise TemplateError("pinned or custom component source; use a custom config")
    return ref


def _protection(fields: dict[str, Node]) -> tuple[Value | None, Value | None, Value | None, bool]:
    """Read the API and native OTA protection of a standalone builder template."""
    api_key = None
    api = fields.get("api")
    if api is None:
        raise TemplateError("templates without the native API must be managed as custom configs")
    if api.tag != "tag:yaml.org,2002:null":
        api_fields = _mapping(api, "API")
        if "password" in api_fields:
            raise TemplateError("legacy API password; use a custom config")
        if "encryption" in api_fields:
            encryption = _mapping(api_fields["encryption"], "API encryption")
            if encryption.keys() != {"key"}:
                raise TemplateError("unsupported API encryption options; use a custom config")
            api_key = _credential(encryption["key"], "API encryption")

    ota = fields.get("ota")
    if (
        not isinstance(ota, SequenceNode)
        or ota.tag != "tag:yaml.org,2002:seq"
        or len(ota.value) != 1
    ):
        raise TemplateError("unsupported encrypted OTA or transport layout; use a custom config")
    native = _mapping(ota.value[0], "OTA")
    if _string(native.get("platform")) != "esphome":
        raise TemplateError("unsupported OTA platform; use a custom config")
    if native.keys() - {"platform", "password", "encryption"}:
        raise TemplateError("unsupported OTA options; use a custom config")
    if "encryption" in native:
        if "password" in native:
            raise TemplateError("unsupported OTA encryption options; use a custom config")
        node = native["encryption"]
        encryption = {} if node.tag == "tag:yaml.org,2002:null" else _mapping(node, "encrypted OTA")
        if not encryption and api_key is not None:
            return api_key, None, None, True
        if encryption.keys() != {"key"}:
            raise TemplateError("unsupported OTA encryption options; use a custom config")
        return api_key, None, _credential(encryption["key"], "OTA encryption"), False
    password = _credential(native["password"], "OTA password") if "password" in native else None
    return api_key, password, None, False


def config_values(config_text: str) -> ConfigValues:
    """Name, API key, OTA password and channel as a config sets them."""
    name_match = re.search(r"(?m)^  device_name:\s*(\S+)", config_text)
    if name_match is None:
        name_match = re.search(r"(?m)^esphome:\s*\n(?:[ \t]+.*\n)*?  name:\s*(\S+)", config_text)
    if name_match is None or "${" in name_match.group(1):
        raise TemplateError("the config has no device name")
    name = name_match.group(1).strip("'\"")

    fields = _template_fields(config_text)
    api_key, ota_password, ota_encryption_key, ota_uses_api_key = _protection(fields)
    channel = _template_channel(fields)

    return ConfigValues(
        name=name,
        api_key=api_key,
        ota_password=ota_password,
        channel=channel,
        ota_encryption_key=ota_encryption_key,
        ota_uses_api_key=ota_uses_api_key,
    )


# --- rendering ----------------------------------------------------------------


def _sub_once(pattern: str, repl: str, text: str, what: str) -> str:
    new, count = re.subn(pattern, lambda _: repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise TemplateError(f"builder file has no {what}")
    return new


def _body(template_text: str) -> str:
    """A builder file without its leading comments (repo notes, an old marker)."""
    lines = template_text.replace("\r\n", "\n").split("\n")
    start = 0
    while start < len(lines) and (not lines[start].strip() or lines[start].startswith("#")):
        start += 1
    return "\n".join(lines[start:])


def _folder(template: Template) -> str:
    return template.file.split("/")[1]


def _template_header(template: Template) -> str:
    variant = VARIANT_TITLES.get(template.variant, template.variant)
    return "\n".join(
        [
            f"{MARKER_PREFIX}{template.file}",
            f"# Made by Levoit ESPHome from the template above ({template.title}, {variant}).",
            "# Every update rewrites this file from the newest template, keeping the name,",
            "# secrets and channel. To change anything else, DELETE THE FIRST LINE first:",
            "# the config is then your own (custom), and updates only build the newer",
            "# component it pulls (ref: below).",
            f"# Wiring and pins: {DEVICES_URL}{_folder(template)}",
            "",
            "",
        ]
    )


def _custom_header(template: Template, esp: CustomEsp) -> str:
    return "\n".join(
        [
            f"# Made by Levoit ESPHome from {template.file} ({template.title})",
            f"# for your own ESP: board {esp.board}, UART RX {esp.rx_pin} / TX {esp.tx_pin}.",
            "# A custom config: updates never rewrite it, they only build the newer",
            "# component it pulls (ref: below).",
            f"# Wiring and pins: {DEVICES_URL}{_folder(template)}",
            "",
            "",
        ]
    )


def render(template_text: str, template: Template, values: ConfigValues) -> str:
    """The builder file with the device's own values, under the marker line.

    The repo notes at the top of a builder file (how it is generated) give way
    to a header that says the file follows the template, and how to make it
    your own: delete the first line.
    """
    return _apply_values(_template_header(template) + _body(template_text), values)


def render_custom(
    template_text: str, template: Template, values: ConfigValues, esp: CustomEsp
) -> str:
    """A custom config: a builder file for another board and other UART pins.

    No marker line: it is never rewritten, updates only build the component.
    """
    text = _apply_values(_custom_header(template, esp) + _body(template_text), values)
    text = _sub_once(
        r"^esp32:[ \t]*\n(?:[ \t]+.*\n|[ \t]*\n)*",
        f"esp32:\n  board: {esp.board}\n  framework:\n    type: esp-idf\n\n",
        text,
        "esp32 block",
    )
    text = _sub_once(r"^  rx_pin:.*$", f"  rx_pin: {esp.rx_pin}", text, "rx_pin")
    return _sub_once(r"^  tx_pin:.*$", f"  tx_pin: {esp.tx_pin}", text, "tx_pin")


def builder_esp(template_text: str) -> CustomEsp:
    """Board and UART pins of a builder file (the defaults for a custom config)."""

    def find(pattern: str) -> str:
        match = re.search(pattern, template_text, re.MULTILINE)
        return match.group(1) if match else ""

    return CustomEsp(
        board=find(r"^esp32:[ \t]*\n(?:[ \t]+.*\n)*?  board:\s*(\S+)"),
        rx_pin=find(r"^  rx_pin:\s*([^\s#]+)"),
        tx_pin=find(r"^  tx_pin:\s*([^\s#]+)"),
    )


def valid_board(board: str) -> bool:
    """An ESPHome board name, e.g. seeed_xiao_esp32s3 or esp32-c6-devkitc-1."""
    return bool(_BOARD.match(board))


def normalize_pin(pin: str) -> str | None:
    """GPIO5, gpio05 or 5 -> GPIO5; None if it is not a GPIO number."""
    match = _PIN.match(pin.strip())
    return f"GPIO{int(match.group(1))}" if match else None


def _apply_values(text: str, values: ConfigValues) -> str:
    """The device's name, API and OTA credentials, and channel."""
    text = _sub_once(
        r"^  device_name:\s*\S+[ \t]*$", f"  device_name: {values.name}", text, "device_name"
    )

    if values.api_key is None:
        text = _sub_once(r"^  encryption:[ \t]*\n    key:.*\n", "", text, "api encryption key")
    else:
        text = _sub_once(
            r"^    key: !secret api_key[ \t]*$", f"    key: {values.api_key.yaml}", text, "api key"
        )

    ota_credential = ""
    if values.ota_uses_api_key or values.ota_encryption_key is not None:
        if values.ota_password is not None:
            raise TemplateError("OTA encryption and password must not be combined")
        if values.ota_uses_api_key and (
            values.api_key is None or values.ota_encryption_key is not None
        ):
            raise TemplateError("inherited OTA encryption requires only an API key")
        ota_credential = "    encryption:\n"
        if values.ota_encryption_key is not None:
            ota_credential += f"      key: {values.ota_encryption_key.yaml}\n"
    elif values.ota_password is not None:
        ota_credential = f"    password: {values.ota_password.yaml}\n"

    # The generated native OTA stanza may start out password-based or encrypted.
    text = _sub_once(
        r"^  - platform: esphome[ \t]*\n"
        r"    (?:password: !secret ota_password|encryption:(?: \{\})?"
        r"(?:[ \t]*\n      key: !secret (?:api_key|ota_key))?)[ \t]*\n",
        "  - platform: esphome\n" + ota_credential,
        text,
        "ota credential",
    )

    if values.channel in (CHANNEL_STABLE, CHANNEL_MAIN):
        text = with_channel(text, values.channel)
    return text


# ESPHome 2026.9.0 brought OTA encryption, and from then on a firmware with an
# API key offers it; the uploader of that version and later uses it.
OTA_ENCRYPTION_SINCE = (2026, 9, 0)
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def supports_ota_encryption(esphome_version: str | None) -> bool:
    """Whether an ESPHome version builds and uploads encrypted OTA; unknown counts as yes."""
    if not esphome_version:
        return True
    match = _VERSION.match(esphome_version.strip())
    if match is None:
        return True
    return tuple(int(part) for part in match.groups()) >= OTA_ENCRYPTION_SINCE


_OTA_PASSWORD_LINE = (
    r"^(  - platform: esphome[ \t]*\n)    password: (?:!secret [A-Za-z0-9_.-]+|\".*\")[ \t]*\n"
)
_OTA_INHERITED_LINE = r"^(  - platform: esphome[ \t]*\n)    encryption:[ \t]*\n(?!      key:)"
# no credential at all under the platform line (an unprotected OTA)
_OTA_BARE_LINE = r"^(  - platform: esphome[ \t]*\n)(?!    (?:password|encryption):)"


def _swap_ota_line(pattern: str, line: str, text: str, what: str) -> str:
    """The one OTA credential line under `- platform: esphome` replaced by `line`."""
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise TemplateError(f"expected exactly one {what}, found {len(matches)}")
    match = matches[0]
    return text[: match.start()] + match.group(1) + line + text[match.end() :]


def ota_encryption_from_password(text: str) -> str:
    """A config's OTA password line replaced by encryption that inherits the API key.

    The migration's second step: text only, the rest of the file stays.
    """
    return _swap_ota_line(_OTA_PASSWORD_LINE, "    encryption:\n", text, "ota password line")


def ota_encryption_from_none(text: str) -> str:
    """Encryption that inherits the API key added to a config's unprotected OTA."""
    return _swap_ota_line(_OTA_BARE_LINE, "    encryption:\n", text, "unprotected ota line")


def ota_password_from_encryption(text: str, secret: str) -> str:
    """The reverse: inherited OTA encryption replaced by `password: !secret <secret>`."""
    return _swap_ota_line(
        _OTA_INHERITED_LINE, f"    password: !secret {secret}\n", text, "ota encryption"
    )


def ota_none_from_encryption(text: str) -> str:
    """Inherited OTA encryption removed: an unprotected OTA again."""
    return _swap_ota_line(_OTA_INHERITED_LINE, "", text, "ota encryption")


def with_channel(text: str, channel: str) -> str:
    """A builder file or template config with its component `ref:` set to `channel`."""
    if channel not in (CHANNEL_STABLE, CHANNEL_MAIN):
        raise TemplateError(f"unknown channel {channel}")
    return _sub_once(r"^      ref: \S+[ \t]*$", f"      ref: {channel}", text, "component ref")


# --- names and keys -----------------------------------------------------------


def valid_name(name: str) -> bool:
    """An ESPHome node name: lowercase letters, digits, hyphens; max 31."""
    return bool(_NAME.match(name))


def suggest_name(base: str, taken: set[str]) -> str:
    """`base`, or `base-2`, `base-3` ... if taken."""
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def secret_key(name: str, what: str) -> str:
    """Secret name for a device: levoit-everest-air-c3 -> levoit_everest_air_c3_api_key."""
    return f"{name.replace('-', '_')}_{what}"


def new_api_key() -> str:
    """An ESPHome API encryption key: 32 random bytes, base64."""
    return base64.b64encode(pysecrets.token_bytes(32)).decode()


def new_ota_password() -> str:
    """A random OTA password."""
    return pysecrets.token_hex(16)
