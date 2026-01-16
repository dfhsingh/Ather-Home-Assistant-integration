"""Button platform for Ather Electric."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AtherCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ather Electric button platform."""
    coordinator: AtherCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            AtherPingButton(coordinator),
            AtherRemoteShutdownButton(coordinator),
        ]
    )


class AtherButton(CoordinatorEntity, ButtonEntity):
    """Base class for Ather buttons."""

    def __init__(self, coordinator: AtherCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.scooter_id)},
            "name": coordinator.device_name,
            "manufacturer": "Ather Energy",
        }


class AtherPingButton(AtherButton):
    """Button to ping the scooter."""

    _attr_name = "Ping My Scooter"
    _attr_unique_id = "ping_my_scooter"
    _attr_icon = "mdi:map-marker-radius"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Pinging scooter...")
        await self.coordinator.async_ping_scooter()


class AtherRemoteShutdownButton(AtherButton):
    """Button to remotely shutdown the scooter."""

    _attr_name = "Remote Shutdown"
    _attr_unique_id = "remote_shutdown"
    _attr_icon = "mdi:power-off"

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.coordinator.shutdown_safe_mode:
            _LOGGER.warning(
                "Remote Shutdown blocked because Safe Mode is ON. "
                "Turn off the Shutdown Protection switch to proceed."
            )
            persistent_notification.async_create(
                self.hass,
                "Remote Shutdown blocked. Disarm 'Shutdown Protection' switch first.",
                title="Ather Electric Safety",
                notification_id="ather_shutdown_block",
            )
            return

        _LOGGER.warning("Initiating Remote Shutdown...")
        await self.coordinator.async_remote_shutdown()
