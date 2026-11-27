"""Config flow (one entry) and the "Add device" subentry flow.

Add device is the plain route: five forms on the integration page, over the
steps in onboarding.py (which the sidebar panel's wizard shares): a new
device or one Home Assistant knows without a config, the model, the ESP (a
template, or the user's own board and pins), name and channel, then the
secrets and the config in the Device Builder.
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

from . import onboarding as onb, templates as tpl
from .const import CHANNEL_MAIN, CHANNEL_STABLE, CONF_SHOW_PANEL, DOMAIN
from .device_builder import async_get_device_builder
from .onboarding import OnboardingError

if TYPE_CHECKING:
    from .coordinator import LevoitDevice, LevoitEsphomeCoordinator


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
        return {onb.SUBENTRY_TYPE: AddDeviceFlow}

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
        # custom: the user's own board and pins, on the template's builder file
        self._custom: tpl.CustomEsp | None = None
        self._source: str | None = None
        self._state: onb.BuilderState | None = None  # the Device Builder's listing

    @property
    def _coordinator(self) -> LevoitEsphomeCoordinator:
        return self._get_entry().runtime_data

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
        if not onb.unconfigured(self._coordinator):
            return await self.async_step_new()
        return self.async_show_menu(step_id="user", menu_options=["new", "existing"])

    async def async_step_existing(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick the device."""
        devices = {d.name: d for d in onb.unconfigured(self._coordinator)}
        if user_input is not None:
            self._existing = devices[user_input["device"]]
            if self._existing.model and onb.variants(self._templates, self._existing.model):
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
        options = [
            SelectOptionDict(value=model, label=title)
            for model, title in onb.models(self._templates)
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
        """Pick the ESP: a template (original, XIAO C3, ...) or custom (own board and pins)."""
        assert self._model is not None
        variants = onb.variants(self._templates, self._model)
        if user_input is not None:
            if user_input["variant"] == tpl.VARIANT_CUSTOM:
                self._template = onb.custom_base(variants)
                return await self.async_step_custom()
            self._template = next(t for t in variants if t.variant == user_input["variant"])
            self._custom = None
            return await self.async_step_details()
        return self.async_show_form(
            step_id="variant",
            data_schema=vol.Schema(
                {
                    vol.Required("variant"): SelectSelector(
                        SelectSelectorConfig(
                            options=[*(t.variant for t in variants), tpl.VARIANT_CUSTOM],
                            translation_key="variant",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"model": variants[0].title},
        )

    async def async_step_custom(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Board and UART pins of the user's own ESP (a custom config)."""
        assert self._template is not None
        if self._source is None:
            try:
                self._source = await tpl.async_fetch_template_text(
                    async_get_clientsession(self.hass), self._template
                )
            except (aiohttp.ClientError, TimeoutError):
                return self.async_abort(reason="templates_unavailable")
        defaults = tpl.builder_esp(self._source)
        errors: dict[str, str] = {}
        if user_input is not None:
            board, rx_pin, tx_pin = (str(user_input[k]) for k in ("board", "rx_pin", "tx_pin"))
            self._custom, errors = onb.validate_custom(board, rx_pin, tx_pin)
            if not errors:
                return await self.async_step_details()
            defaults = tpl.CustomEsp(board=board, rx_pin=rx_pin, tx_pin=tx_pin)
        boards = list(onb.COMMON_BOARDS)
        if defaults.board and defaults.board not in boards:
            boards.insert(0, defaults.board)
        return self.async_show_form(
            step_id="custom",
            data_schema=vol.Schema(
                {
                    vol.Required("board", default=defaults.board): SelectSelector(
                        SelectSelectorConfig(
                            options=boards,
                            custom_value=True,
                            sort=False,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required("rx_pin", default=defaults.rx_pin): TextSelector(),
                    vol.Required("tx_pin", default=defaults.tx_pin): TextSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "model": self._template.title,
                "base": tpl.VARIANT_TITLES.get(self._template.variant, self._template.variant),
            },
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
            self._state = await onb.async_builder_state(self.hass, builder, self._coordinator)
        except OnboardingError as err:
            return self.async_abort(reason=err.code)

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"model": self._template.title}
        if user_input is not None:
            if self._existing is not None:
                name = self._existing.name
            else:
                name = str(user_input["name"]).strip().lower()
                if error := onb.check_name(name, self._state.taken):
                    errors["name"] = error
            if not errors:
                request = onb.DeviceRequest(
                    template=self._template,
                    name=name,
                    channel=user_input["channel"],
                    existing=self._existing is not None,
                    custom=self._custom,
                    ota_password=user_input.get("ota_password") or None,
                    source=self._source,
                )
                try:
                    created = await onb.async_create_device(
                        self.hass, self._coordinator, builder, request, self._state.esphome_version
                    )
                except OnboardingError as err:
                    errors["base"] = err.code
                    placeholders.update(err.placeholders)
                else:
                    return self._async_created(created)

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
            default = (user_input or {}).get("name") or tpl.suggest_name(
                self._template.name, set(self._state.taken)
            )
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

    def _async_created(self, created: onb.CreatedDevice) -> SubentryFlowResult:
        """The device's sub-entry, and what to do next."""
        return self.async_create_entry(
            title=created.name,
            data=created.subentry_data,
            description="existing" if created.existing else None,
            description_placeholders={
                "configuration": created.configuration,
                "name": created.name,
                "builder_url": created.builder_url,
            },
            unique_id=created.name,
        )


def _channel_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[CHANNEL_STABLE, CHANNEL_MAIN],
            translation_key="channel",
            mode=SelectSelectorMode.LIST,
        )
    )
