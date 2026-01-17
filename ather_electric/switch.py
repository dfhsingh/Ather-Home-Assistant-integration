"""Switch platform for Ather Electric."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
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
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:battery-charging"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_remote_charging"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Check for chargingHeartBeat as requested by user
        if not self.coordinator.last_update_success:
            return False

        charging_data = self.coordinator.get_data("charging", {})
        return charging_data.get("chargingHeartBeat") == "On"

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        charging_data = self.coordinator.get_data("charging", {})
        status = charging_data.get("chargingStatus")
        return status == "Charging"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.coordinator.async_remote_charging("start")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.coordinator.async_remote_charging("stop")


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
