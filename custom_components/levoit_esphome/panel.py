"""Sidebar panel and dashboard cards.

The panel is a Levoit ESPHome page for admins, behind the show_panel option.
The dashboard cards (levoit-esphome-cards.js) load on every page for every
user, so they can be added to any dashboard without a resource of their own.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, PANEL_COMPONENT, PANEL_STATIC_URL, PANEL_URL_PATH

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = "levoit-esphome-panel.js"
CARDS_FILE = "levoit-esphome-cards.js"
# static paths cannot be removed again: registered once per Home Assistant run
_STATIC_REGISTERED: HassKey[bool] = HassKey(f"{DOMAIN}_static")
_CARDS_URL: HassKey[str] = HassKey(f"{DOMAIN}_cards_url")


async def _async_serve_frontend(hass: HomeAssistant) -> None:
    """Serve the frontend folder (once per run)."""
    if hass.data.get(_STATIC_REGISTERED):
        return
    if hass.http is None:  # no web server (tests)
        _LOGGER.debug("No web server: frontend files not served")
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    hass.data[_STATIC_REGISTERED] = True


async def async_register_cards(hass: HomeAssistant) -> None:
    """Load the dashboard cards on every page (any user)."""
    await _async_serve_frontend(hass)
    if hass.data.get(_CARDS_URL) or "frontend" not in hass.config.components:
        return
    version = (await async_get_integration(hass, DOMAIN)).version
    # the version makes browsers load a new file after an update
    url = f"{PANEL_STATIC_URL}/{CARDS_FILE}?v={version}"
    frontend.add_extra_js_url(hass, url)
    hass.data[_CARDS_URL] = url


@callback
def async_remove_cards(hass: HomeAssistant) -> None:
    """Stop loading the dashboard cards (unload)."""
    if url := hass.data.pop(_CARDS_URL, None):
        frontend.remove_extra_js_url(hass, url)


async def async_register_panel(hass: HomeAssistant) -> None:
    """Add the sidebar entry (admins only)."""
    await _async_serve_frontend(hass)
    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Levoit ESPHome",
        sidebar_icon="mdi:air-purifier",
        # the version makes browsers load a new panel file after an update
        module_url=f"{PANEL_STATIC_URL}/{PANEL_FILE}?v={version}",
        require_admin=True,
        config={"version": str(version)},
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar entry."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
