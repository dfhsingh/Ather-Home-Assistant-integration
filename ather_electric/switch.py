"""Switch platform for Ather Electric."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up the Ather Electric switch platform."""
    coordinator: AtherCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    features = coordinator.data.get("features", {})

    if features.get("atherStackRemoteCharging") == 1:
        entities.append(AtherRemoteChargingSwitch(coordinator))

    # Only add protection switch if remote shutdown is enabled
    if features.get("atherStackRemoteShutdown") == 1:
        entities.append(AtherShutdownProtectionSwitch(coordinator))

    async_add_entities(entities)


class AtherSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for Ather switches."""

    def __init__(self, coordinator: AtherCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.scooter_id)},
            "name": coordinator.device_name,
            "manufacturer": "Ather Energy",
        }


class AtherRemoteChargingSwitch(AtherSwitch):
    """Switch to control remote charging."""

    _attr_name = "Remote Charging"
    _attr_unique_id = "remote_charging"
    _attr_icon = "mdi:battery-charging"

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        # Check 'charging' status from coordinator data
        # Example data: 'charging': {'status': 'charging', ...} or similar
        # If unknown, we might default to False or check data structure carefully
        charging_data = self.coordinator.data.get("charging", {})
        # This logic might need adjustment based on actual API response values
        # Common values: "charging", "not_charging", "optimised_charging_on"
        # Since we are controlling "Remote Charging" (which might physically enable the charger),
        # we can assume if status implies charging, it's ON.
        # However, accurate feedback depends on the scooter's response.
        status = charging_data.get("status", "").lower()
        return status in ["charging", "optimised_charging_on", "soc_reached_100"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.coordinator.async_remote_charging("start")
        # Optimistic update or wait for next poll/push
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.coordinator.async_remote_charging("stop")
        self.async_write_ha_state()


class AtherShutdownProtectionSwitch(AtherSwitch):
    """Switch to toggle Shutdown Safety Mode."""

    _attr_name = "Shutdown Protection"
    _attr_unique_id = "shutdown_protection"
    _attr_icon = "mdi:shield-lock"
    _attr_entity_category = EntityCategory.CONFIG  # Show in configuration section

    @property
    def is_on(self) -> bool:
        """Return true if safe mode is on."""
        return self.coordinator.shutdown_safe_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable safe mode."""
        self.coordinator.shutdown_safe_mode = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable safe mode."""
        self.coordinator.shutdown_safe_mode = False
        self.async_write_ha_state()
