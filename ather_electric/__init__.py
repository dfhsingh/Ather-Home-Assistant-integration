"""The Ather Electric integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_FIREBASE_API_KEY,
    CONF_FIREBASE_TOKEN,
    CONF_SCOOTER_ID,
    DOMAIN,
    PLATFORMS,
    FIREBASE_API_KEY,
)
from .coordinator import AtherCoordinator

_LOGGER = logging.getLogger(__name__)

# Configuration Schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_SCOOTER_ID): cv.string,
                vol.Required(CONF_FIREBASE_TOKEN): cv.string,
                vol.Optional(CONF_FIREBASE_API_KEY): cv.string,
                vol.Optional(CONF_NAME, default="Ather Scooter"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ather Electric integration."""
    conf = config.get(DOMAIN)
    if conf is None:
        return True

    # Ensure API Key is present for import if missing
    if CONF_FIREBASE_API_KEY not in conf:
        conf[CONF_FIREBASE_API_KEY] = FIREBASE_API_KEY

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data=conf,
        )
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up Ather Electric from a config entry."""
    scooter_id = entry.data[CONF_SCOOTER_ID]
    firebase_token = entry.data[CONF_FIREBASE_TOKEN]
    # Use constant if not in entry (migration or hardcoded preference)
    api_key = entry.data.get(CONF_FIREBASE_API_KEY, FIREBASE_API_KEY)
    device_name = entry.data.get(CONF_NAME, "Ather Scooter")

    coordinator = AtherCoordinator(
        hass, scooter_id, firebase_token, api_key, device_name
    )

    # Start the coordinator (WebSocket connection)
    hass.loop.create_task(coordinator.connect())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
