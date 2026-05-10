"""The Ather Electric (Binary) integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    CONF_FIREBASE_API_KEY,
    CONF_FIREBASE_TOKEN,
    CONF_SCOOTER_ID,
    DOMAIN,
    PLATFORMS,
    CONF_BASE_URL,
)
from .coordinator import AtherCoordinator
from .api import AtherAPI

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ather Electric (Binary) integration."""
    return True

async def async_setup_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up Ather Electric (Binary) from a config entry."""
    if CONF_SCOOTER_ID not in entry.data:
        _LOGGER.error("Scooter ID not found in configuration. Please remove and re-add the integration.")
        return False

    scooter_id = entry.data[CONF_SCOOTER_ID]
    firebase_token = entry.data[CONF_FIREBASE_TOKEN]
    api_token = entry.data.get("api_token")
    api_key = entry.data.get(CONF_FIREBASE_API_KEY) # May be missing if using binary secrets
    device_name = entry.data.get(CONF_NAME, "Ather Scooter")
    base_url = entry.data.get(CONF_BASE_URL)

    integration = await async_get_integration(hass, DOMAIN)
    integration_version = integration.version

    # Initialize RideManager
    from .ride_manager import RideManager
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    
    # AtherAPI will use embedded secrets for critical tasks
    ride_api_client = AtherAPI(
        session,
        base_url=base_url if base_url else "https://ather-production.firebaseio.com",
    )

    ride_manager = RideManager(
        hass,
        ride_api_client,
        scooter_id,
        api_token,
    )

    # Wait for DB Init
    await ride_manager.async_init()

    coordinator = AtherCoordinator(
        hass,
        scooter_id,
        firebase_token,
        api_token,
        api_key,
        device_name,
        integration_version,
        base_url=base_url,
        ride_manager=ride_manager,
    )

    # Start the coordinator (WebSocket connection)
    coordinator.start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Wait for initial data to ensure feature flags are loaded
    try:
        await asyncio.wait_for(coordinator.async_wait_for_initial_data(), timeout=60)
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
