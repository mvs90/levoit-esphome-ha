"""Config flow (one entry) and the "Add device" subentry flow.

Add device makes a Device Builder config from a template of tuct/levoit
(devices/templates.json: a model, original ESP, ESP32-C3 or ESP32-S3):

* new device: suggested name, generated API encryption key and OTA password,
  stored in secrets.yaml as <name>_api_key / <name>_ota_password
* existing device (in Home Assistant, but no Device Builder config): its name,
  its API key from the ESPHome config entry, its OTA password as entered

Wi-Fi comes from the shared wifi_ssid / wifi_password / wifi_ap_password
secrets, which must exist. Only secret names are read, never values; a secret
that exists is never overwritten.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import templates as tpl
from .const import CHANNEL_MAIN, CHANNEL_STABLE, CONF_SHOW_PANEL, DOMAIN
from .device_builder import (
    DeviceBuilderCommandError,
    async_add_secret,
    async_create_config,
    async_get_device_builder,
    async_secret_names,
    builder_page_url,
)

if TYPE_CHECKING:
    from .coordinator import LevoitDevice, LevoitEsphomeCoordinator

WIFI_SECRETS = ("wifi_ssid", "wifi_password", "wifi_ap_password")
ESPHOME_DOMAIN = "esphome"


class LevoitEsphomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Levoit ESPHome."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm; abort without a Device Builder."""
        if async_get_device_builder(self.hass) is None:
            return self.async_abort(reason="no_device_builder")
        if user_input is not None:
            return self.async_create_entry(title="Levoit ESPHome", data={})
        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """The "Add device" button."""
        return {"device": AddDeviceFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options: the sidebar panel."""
        return LevoitEsphomeOptionsFlow()


class LevoitEsphomeOptionsFlow(OptionsFlow):
    """Show the Levoit ESPHome page in the sidebar (admins only)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The switch; saving sets the entry up again, which adds or removes the panel."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SHOW_PANEL,
                        default=self.config_entry.options.get(CONF_SHOW_PANEL, False),
                    ): BooleanSelector()
                }
            ),
        )


class AddDeviceFlow(ConfigSubentryFlow):
    """Make a Device Builder config from a template, for a new or an existing device."""

    def __init__(self) -> None:
        """Initialize."""
        self._templates: list[tpl.Template] = []
        self._model: str | None = None
        self._template: tpl.Template | None = None
        self._existing: LevoitDevice | None = None

    @property
    def _coordinator(self) -> LevoitEsphomeCoordinator:
        return self._get_entry().runtime_data

    def _unconfigured(self) -> list[LevoitDevice]:
        data = self._coordinator.data
        return [d for d in data.devices.values() if not d.configuration] if data else []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """New device, or one Home Assistant knows without a Device Builder config."""
        if async_get_device_builder(self.hass) is None:
            return self.async_abort(reason="no_device_builder")
        try:
            self._templates = await self._coordinator.async_get_templates()
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError):
            return self.async_abort(reason="templates_unavailable")
        if not self._templates:
            return self.async_abort(reason="templates_unavailable")
        if not self._unconfigured():
            return await self.async_step_new()
        return self.async_show_menu(step_id="user", menu_options=["new", "existing"])

    async def async_step_existing(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick the device."""
        devices = {d.name: d for d in self._unconfigured()}
        if user_input is not None:
            self._existing = devices[user_input["device"]]
            if self._existing.model and any(
                t.model == self._existing.model for t in self._templates
            ):
                self._model = self._existing.model
                return await self.async_step_variant()
            return await self.async_step_new()
        options = [SelectOptionDict(value=d.name, label=d.title) for d in devices.values()]
        return self.async_show_form(
            step_id="existing",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def async_step_new(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Pick the model."""
        if user_input is not None:
            self._model = user_input["model"]
            return await self.async_step_variant()
        models: dict[str, str] = {}
        for template in self._templates:
            models.setdefault(template.model, template.title)
        options = [
            SelectOptionDict(value=model, label=title)
            for model, title in sorted(models.items(), key=lambda item: item[1])
        ]
        return self.async_show_form(
            step_id="new",
            data_schema=vol.Schema(
                {
                    vol.Required("model"): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def async_step_variant(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick original ESP or ESP32-C3 (skipped when there is only one)."""
        variants = [t for t in self._templates if t.model == self._model]
        if user_input is not None:
            self._template = next(t for t in variants if t.variant == user_input["variant"])
            return await self.async_step_details()
        if len(variants) == 1:
            self._template = variants[0]
            return await self.async_step_details()
        return self.async_show_form(
            step_id="variant",
            data_schema=vol.Schema(
                {
                    vol.Required("variant"): SelectSelector(
                        SelectSelectorConfig(
                            options=[t.variant for t in variants],
                            translation_key="variant",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"model": variants[0].title},
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Name and channel (new), or channel and OTA password (existing)."""
        assert self._template is not None
        builder = async_get_device_builder(self.hass)
        if builder is None:
            return self.async_abort(reason="no_device_builder")
        try:
            listing = await builder.api.get_devices()
        except (aiohttp.ClientError, TimeoutError):
            return self.async_abort(reason="cannot_connect")
        taken = {d["name"] for d in listing.get("configured", []) if d.get("name")}
        taken |= set(self._coordinator.data.devices) if self._coordinator.data else set()

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"model": self._template.title}
        if user_input is not None:
            if self._existing is not None:
                name = self._existing.name
            else:
                name = str(user_input["name"]).strip().lower()
                if not tpl.valid_name(name):
                    errors["name"] = "invalid_name"
                elif name in taken:
                    errors["name"] = "name_taken"
            if not errors:
                result = await self._async_create(
                    name,
                    user_input["channel"],
                    user_input.get("ota_password") or None,
                    errors,
                    placeholders,
                )
                if result is not None:
                    return result

        if self._existing is not None:
            schema = vol.Schema(
                {
                    vol.Required("channel", default=CHANNEL_STABLE): _channel_selector(),
                    vol.Optional("ota_password"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            )
            placeholders["name"] = self._existing.name
            placeholders["api_secret"] = tpl.secret_key(self._existing.name, "api_key")
            step_id = "details_existing"
        else:
            default = (user_input or {}).get("name") or tpl.suggest_name(self._template.name, taken)
            schema = vol.Schema(
                {
                    vol.Required("name", default=default): TextSelector(),
                    vol.Required("channel", default=CHANNEL_STABLE): _channel_selector(),
                }
            )
            step_id = "details"
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    # the details_existing form posts to its own step id
    async_step_details_existing = async_step_details

    async def _async_create(
        self,
        name: str,
        channel: str,
        ota_password: str | None,
        errors: dict[str, str],
        placeholders: dict[str, str],
    ) -> SubentryFlowResult | None:
        """Secrets, then the config. None (with `errors` set) if it did not work."""
        assert self._template is not None
        builder = async_get_device_builder(self.hass)
        if builder is None:
            return self.async_abort(reason="no_device_builder")

        # what goes into secrets.yaml
        api_secret = tpl.secret_key(name, "api_key")
        ota_secret = tpl.secret_key(name, "ota_password")
        new_secrets: dict[str, str] = {}
        if self._existing is None:
            new_secrets[api_secret] = tpl.new_api_key()
            new_secrets[ota_secret] = tpl.new_ota_password()
        else:
            if api_key := self._existing_api_key(name):
                new_secrets[api_secret] = api_key
            if ota_password:
                new_secrets[ota_secret] = ota_password

        try:
            present = await async_secret_names(self.hass, builder)
            if missing := [key for key in WIFI_SECRETS if key not in present]:
                errors["base"] = "missing_wifi_secrets"
                placeholders["missing"] = ", ".join(missing)
                return None
            if exists := [key for key in new_secrets if key in present]:
                errors["base"] = "secret_exists"
                placeholders["secret"] = ", ".join(exists)
                return None

            source = await tpl.async_fetch_template_text(
                async_get_clientsession(self.hass), self._template
            )
            content = tpl.render(
                source,
                self._template,
                tpl.ConfigValues(
                    name=name,
                    api_key=tpl.Value(secret=api_secret) if api_secret in new_secrets else None,
                    ota_password=tpl.Value(secret=ota_secret)
                    if ota_secret in new_secrets
                    else None,
                    channel=channel,
                ),
            )

            for key, value in new_secrets.items():
                if not await async_add_secret(self.hass, builder, key, value):
                    errors["base"] = "secret_exists"
                    placeholders["secret"] = key
                    return None
            configuration = await async_create_config(self.hass, builder, name, content)
        except DeviceBuilderCommandError as err:
            errors["base"] = "config_exists" if err.code == "already_exists" else "cannot_connect"
            return None
        except (aiohttp.ClientError, TimeoutError, tpl.TemplateError):
            errors["base"] = "template_failed"
            return None

        await self._coordinator.async_request_refresh()
        return self.async_create_entry(
            title=name,
            data={
                "configuration": configuration,
                "template": self._template.file,
                "existing": self._existing is not None,
            },
            description="existing" if self._existing is not None else None,
            description_placeholders={
                "configuration": configuration,
                "name": name,
                "builder_url": builder_page_url(builder)
                or "/config/integrations/integration/esphome",
            },
            unique_id=name,
        )

    def _existing_api_key(self, name: str) -> str | None:
        """The API encryption key Home Assistant uses for the device, if any."""
        for entry in self.hass.config_entries.async_entries(ESPHOME_DOMAIN):
            if entry.data.get("device_name") == name:
                return entry.data.get("noise_psk") or None
        return None


def _channel_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[CHANNEL_STABLE, CHANNEL_MAIN],
            translation_key="channel",
            mode=SelectSelectorMode.LIST,
        )
    )
