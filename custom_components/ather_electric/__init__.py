"""The Ather Electric integration."""

from __future__ import annotations

import asyncio
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
    CONF_BASE_URL,
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


from homeassistant.loader import async_get_integration

# ... existing imports ...


async def async_setup_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up Ather Electric from a config entry."""
    scooter_id = entry.data[CONF_SCOOTER_ID]
    firebase_token = entry.data[CONF_FIREBASE_TOKEN]
    api_token = entry.data.get("api_token")
    api_key = entry.data[CONF_FIREBASE_API_KEY]
    device_name = entry.data.get(CONF_NAME, "Ather Scooter")
    base_url = entry.data.get(CONF_BASE_URL)

    integration = await async_get_integration(hass, DOMAIN)
    integration_version = integration.version

    coordinator = AtherCoordinator(
        hass,
        scooter_id,
        firebase_token,
        api_token,
        api_key,
        device_name,
        integration_version,
        base_url=base_url,
    )

    # Start the coordinator (WebSocket connection)
    coordinator.start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Wait for initial data to ensure feature flags are loaded
    try:
        await asyncio.wait_for(coordinator.async_wait_for_initial_data(), timeout=10)
    except asyncio.TimeoutError:
        _LOGGER.warning(
            "Timed out waiting for initial data. Remote features may not be enabled."
        )
    except Exception as err:
        _LOGGER.error("Error waiting for initial data: %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Apply initial options
    if entry.options:
        coordinator.set_options(entry.options)

    # Register update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: config_entries.ConfigEntry):
    """Handle options update."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.set_options(entry.options)


async def async_unload_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.close()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
