"""Binary sensor platform for Ather Electric."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
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
        AtherChargingHeartbeatSensor(coordinator),
        AtherVacationModeSensor(coordinator),
        # Diagnostic Feature Flags
        AtherFeatureBinarySensor(
            coordinator, "vehicle_fallDetection", "Fall Detection"
        ),
        AtherFeatureBinarySensor(coordinator, "vehicle_hillAssist", "Hill Assist"),
        AtherFeatureBinarySensor(coordinator, "vehicle_theftTow", "Theft & Tow"),
        AtherFeatureBinarySensor(coordinator, "vehicle_smartEco", "Smart Eco"),
        AtherFeatureBinarySensor(coordinator, "warp_mode", "Warp Mode"),
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


class AtherChargingHeartbeatSensor(AtherBinarySensor):
    """Representation of the Charging Heartbeat (Diagnostic)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Charging Heartbeat"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_charging_heartbeat"

    @property
    def is_on(self) -> bool | None:
        """Return true if heartbeat is On."""
        charging_data = self.coordinator.get_data("charging", {})
        return charging_data.get("chargingHeartBeat") == "On"


class AtherVacationModeSensor(AtherBinarySensor):
    """Representation of the Vacation/Shutdown Mode."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_name = "Vacation Mode"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_vacation"

    @property
    def is_on(self) -> bool | None:
        """Return true if vacation mode is active."""
        # Log: "ShutdownVacationMode": 1
        val = self.coordinator.get_data("ShutdownVacationMode")
        return safe_bool(val)


class AtherFeatureBinarySensor(AtherBinarySensor):
    """Representation of a generic feature flag (Diagnostic)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, feature_key: str, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.feature_key = feature_key
        self._attr_name = name
        self._id_suffix = feature_key.lower().replace("_", "_")

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_feature_{self._id_suffix}"

    @property
    def is_on(self) -> bool | None:
        """Return true if feature is enabled."""
        # features is a dict
        features = self.coordinator.get_data("features", {})
        if features:
            val = features.get(self.feature_key)
            return safe_bool(val)
        return None


def safe_bool(value) -> bool:
    """Safely convert to bool."""
    if value in [1, "1", True, "True", "true", "On", "on"]:
        return True
    return False
