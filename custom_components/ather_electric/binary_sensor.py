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
        AtherChargingPredictionSensor(coordinator),
        AtherChargingHeartbeatSensor(coordinator),
        AtherVacationModeSensor(coordinator),
        # Active Status Sensors
        AtherParkingAssistStatusSensor(coordinator),
        AtherCruiseControlStatusSensor(coordinator),
        # Diagnostic Feature Flags
        AtherFeatureBinarySensor(
            coordinator, "vehicle_parkAssist", "Parking Assist Feature", "mdi:parking"
        ),
        AtherFeatureBinarySensor(
            coordinator,
            "vehicle_cruiseControl",
            "Cruise Control Feature",
            "mdi:speedometer-auto",
        ),
        AtherFeatureBinarySensor(
            coordinator, "vehicle_fallDetection", "Fall Detection", "mdi:alert-box"
        ),
        AtherFeatureBinarySensor(coordinator, "vehicle_hillAssist", "Hill Assist"),
        AtherFeatureBinarySensor(coordinator, "vehicle_theftTow", "Theft & Tow"),
        AtherFeatureBinarySensor(coordinator, "vehicle_smartEco", "Smart Eco"),
        AtherFeatureBinarySensor(coordinator, "warp_mode", "Warp Mode"),
        AtherIncognitoSensor(coordinator),
        # New Feature Flags & Diagnostics
        AtherFeatureBinarySensor(
            coordinator, "atherStackCrashAlert", "Crash Alert", "mdi:car-crash"
        ),
        AtherFeatureBinarySensor(
            coordinator, "atherStackUnsafeParking", "Unsafe Parking", "mdi:parking"
        ),
        AtherFeatureBinarySensor(
            coordinator, "vehicle_autoIndicator", "Auto Indicator", "mdi:indicator"
        ),
        # Remote Operations Features
        AtherFeatureBinarySensor(
            coordinator,
            "atherStackRemoteCharging",
            "Remote Charging Feature",
            "mdi:battery-charging-wireless",
        ),
        AtherFeatureBinarySensor(
            coordinator,
            "atherStackRemoteShutdown",
            "Remote Shutdown Feature",
            "mdi:power",
        ),
        AtherFeatureBinarySensor(
            coordinator,
            "atherStackPingMyScooter",
            "Find My Scooter Feature",
            "mdi:map-marker-radius",
        ),
        # Advanced Vehicle Features
        AtherFeatureBinarySensor(
            coordinator,
            "vehicle_smartCharging",
            "Smart Charging Feature",
            "mdi:battery-sync",
        ),
        AtherFeatureBinarySensor(
            coordinator, "vehicle_tcsEnable", "TCS Feature", "mdi:tire"
        ),
        AtherFeatureBinarySensor(
            coordinator, "vehicle_guideMeHome", "Guide Me Home", "mdi:lightbulb-on"
        ),
        AtherFeatureBinarySensor(
            coordinator, "vehicle_publicCharging", "Public Charging", "mdi:ev-station"
        ),
        AtherFeatureBinarySensor(
            coordinator,
            "atherStackLiveLocation",
            "Live Location Sharing",
            "mdi:share-variant",
        ),
        AtherFeatureBinarySensor(
            coordinator, "atherStackSportsScore", "Sports Score Widget", "mdi:trophy"
        ),
        AtherPropertyBinarySensor(
            coordinator, "Bluetooth Status", "bt_enabled_device", "mdi:bluetooth"
        ),
    ]

    async_add_entities(entities)


class AtherBinarySensor(BinarySensorEntity):
    """Base class for Ather binary sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_has_entity_name = True
        # Construct dynamic model name if colour is available
        model_name = coordinator.get_data("model_type") or "450X"
        colour = coordinator.get_data("colour")
        if colour:
            model_name = f"{model_name} ({colour})"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.scooter_id)},
            name=coordinator.device_name,
            manufacturer="Ather Energy",
            model=model_name,
            hw_version=coordinator.get_data("model"),  # e.g. "xhr"
            sw_version=f"{coordinator.get_data('UserFacingSoftwareVersion')} (v{coordinator.integration_version})",
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.coordinator.async_add_listener(self.async_write_ha_state)

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        attrs = {}
        updated_at = self.coordinator.get_data("updatedAt")
        if updated_at:
            attrs["updated_at"] = updated_at
        return attrs


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


class AtherChargingPredictionSensor(AtherBinarySensor):
    """Representation of Charging Prediction (Smart Charge)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

    _attr_name = "Charging Prediction"
    _attr_icon = "mdi:battery-charging-high"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_charging_prediction"

    @property
    def is_on(self) -> bool | None:
        """Return true if prediction is active."""
        # Data is in app -> charging_prediction
        # We need to access it via coordinator.data.get("app") if it exists,
        # or coordinator.data if flattened.
        # Log showed: "b": {"p": ".../app", "d": {"charging_prediction": false}}
        # Recursive merge ensures "app" key exists if "d" was a dict.
        val = self.coordinator.get_data("app", {}).get("charging_prediction")
        return safe_bool(val)


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

    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_vacation"

    @property
    def is_on(self) -> bool | None:
        """Return true if vacation mode is active."""
        # Log: "ShutdownVacationMode": 1
        val = self.coordinator.get_data("ShutdownVacationMode")
        return safe_bool(val)


class AtherParkingAssistStatusSensor(AtherBinarySensor):
    """Representation of the Parking Assist status (Active)."""

    _attr_device_class = None  # Generic on/off, or maybe RUNNING?
    _attr_name = "Parking Assist Status"
    _attr_icon = "mdi:parking"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_parking_assist_status"

    @property
    def is_on(self) -> bool | None:
        """Return true if parking assist is active."""
        val = self.coordinator.get_data("parkingAssist")
        return safe_bool(val)


class AtherCruiseControlStatusSensor(AtherBinarySensor):
    """Representation of the Cruise Control status (Active)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_name = "Cruise Control Status"
    _attr_icon = "mdi:speedometer"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_cruise_control_status"

    @property
    def is_on(self) -> bool | None:
        """Return true if cruise control is active."""
        val = self.coordinator.get_data("cruiseControl")
        return safe_bool(val)


class AtherFeatureBinarySensor(AtherBinarySensor):
    """Representation of a generic feature flag (Diagnostic)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator, feature_key: str, name: str, icon: str = None
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.feature_key = feature_key
        self._attr_name = name
        if icon:
            self._attr_icon = icon
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


class AtherIncognitoSensor(AtherBinarySensor):
    """Representation of the Incognito Mode status."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_name = "Incognito Mode"
    _attr_icon = "mdi:incognito"

    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_incognito"

    @property
    def is_on(self) -> bool | None:
        """Return true if incognito mode is active."""
        settings = self.coordinator.get_data("settings", {})
        val = settings.get("incognitoMode")
        return safe_bool(val)


class AtherPropertyBinarySensor(AtherBinarySensor):
    """Binary sensor for hardware properties (bt, etc)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator, name: str, property_key: str, icon: str = None
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = name
        self._property_key = property_key
        if icon:
            self._attr_icon = icon

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_{self._property_key}"

    @property
    def is_on(self) -> bool | None:
        props = self.coordinator.get_data("properties", {})
        val = props.get(self._property_key)
        return safe_bool(val)
