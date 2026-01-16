"""Binary sensor platform for Ather Electric."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ather Electric binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        AtherChargingSensor(coordinator),
        AtherKeySensor(coordinator),
    ]
    # Check if we have data for 'is_locked' or similar keys in real payload before adding
    # For now adding Charging as it is well known (0/1)

    async_add_entities(entities)


class AtherBinarySensor(BinarySensorEntity):
    """Base class for Ather binary sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.scooter_id)},
            name=coordinator.device_name,
            manufacturer="Ather Energy",
            model="450X",
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.coordinator.async_add_listener(self.async_write_ha_state)


class AtherChargingSensor(AtherBinarySensor):
    """Representation of the Charging status."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_name = "Charging Status"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_charging"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        # 'charging' is a dict with 'chargerConnected': "On"/"Off"
        # and 'chargingStatus': "Charging"
        charging_data = self.coordinator.get_data("charging")
        if isinstance(charging_data, dict):
            status = charging_data.get("chargingStatus")
            connected = charging_data.get("chargerConnected")
            return status == "Charging" or connected == "On"
        return None


class AtherKeySensor(AtherBinarySensor):
    """Representation of the Key Switch status."""

    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_name = "Key State"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_key"

    @property
    def is_on(self) -> bool | None:
        """Return true if the key is on (Unlocked/Open)."""
        # keySwitch is "On" or "Off"
        # For DeviceClass.LOCK: On means Unlocked (unsafe), Off means Locked (safe)
        # So "On" -> True (Unlocked) matches nicely?
        # Actually LOCK class: On means Unlocked (problem). Off means Locked (ok).
        # Let's map keySwitch "On" to True (Unlocked).
        val = self.coordinator.get_data("keySwitch")
        if val is None:
            val = self.coordinator.get_data("bike", {}).get("keySwitch")

        return val == "On"
