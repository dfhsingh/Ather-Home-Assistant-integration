"""Sensor platform for Ather Electric."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfSpeed
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ather Electric sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        AtherBatterySensor(coordinator),
        AtherRangeSensor(coordinator),
        AtherSpeedSensor(coordinator),
        AtherRidingModeSensor(coordinator),
        AtherOdoSensor(coordinator),
        AtherVinSensor(coordinator),
        AtherBikeTypeSensor(coordinator),
        AtherOtaStatusSensor(coordinator),
        AtherLastSyncedSensor(coordinator),
        AtherModeRangeSensor(coordinator, "Eco", "EcoModeRange"),
        AtherModeRangeSensor(coordinator, "Ride", "RideModeRange"),
        AtherModeRangeSensor(coordinator, "Sport", "SportModeRange"),
        AtherModeRangeSensor(coordinator, "Warp", "WarpModeRange"),
        AtherModeRangeSensor(coordinator, "SmartEco", "SmartEcoModeRange"),
        AtherAltitudeSensor(coordinator),
        AtherTheftMovementSensor(coordinator),
    ]

    async_add_entities(entities)


class AtherSensor(SensorEntity):
    """Base class for Ather sensors."""

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

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from HA."""
        # Clean up listener if handled by coordinator with remove func,
        # but here we kept it simple list.
        pass


class AtherBatterySensor(AtherSensor):
    """Representation of the Battery SOC sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Battery"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_battery"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("batterySOC")


class AtherRangeSensor(AtherSensor):
    """Representation of the Estimated Range sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Range"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_range"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        # Key might be 'predictedRange' or just 'range', checking both
        return self.coordinator.get_data("predictedRange") or self.coordinator.get_data(
            "range"
        )


class AtherSpeedSensor(AtherSensor):
    """Representation of the Speed sensor."""

    _attr_device_class = SensorDeviceClass.SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Speed"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_speed"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("speed")


class AtherRidingModeSensor(AtherSensor):
    """Representation of the Riding Mode sensor."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_name = "Riding Mode"
    _attr_options = ["Eco", "Ride", "Sport", "Warp", "SmartEco"]

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_mode"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        # Value is string like "Sport", "Eco", etc.
        return self.coordinator.get_data("mode")


class AtherOdoSensor(AtherSensor):
    """Representation of the Odometer sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_name = "Odometer"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_odo"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("odo")


class AtherVinSensor(AtherSensor):
    """Representation of the VIN sensor."""

    _attr_name = "VIN"
    _attr_icon = "mdi:card-account-details"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_vin"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("vin")


class AtherBikeTypeSensor(AtherSensor):
    """Representation of the Bike Type sensor."""

    _attr_name = "Bike Type"
    _attr_icon = "mdi:scooter"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_type"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("bikeType")


class AtherOtaStatusSensor(AtherSensor):
    """Representation of the OTA Status sensor."""

    _attr_name = "OTA Status"
    _attr_icon = "mdi:system-update"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_ota"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("otaStatus")


class AtherLastSyncedSensor(AtherSensor):
    """Representation of the Last Synced Time sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last Synced"
    _attr_icon = "mdi:clock-check"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_last_synced"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        ts_ms = self.coordinator.get_data("lastSyncedTime")
        if ts_ms:
            try:
                # Convert ms timestamp to ISO string for HA
                from datetime import datetime, timezone

                return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            except Exception:
                pass
        return None


class AtherModeRangeSensor(AtherSensor):
    """Representation of the Range for a specific mode."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, mode_name: str, mode_key: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._mode_key = mode_key
        self._attr_name = f"Range ({mode_name})"
        self._id_suffix = mode_name.lower().replace(" ", "_")

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_range_{self._id_suffix}"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        ranges = self.coordinator.get_data("modeRange")
        if ranges and isinstance(ranges, dict):
            return ranges.get(self._mode_key)
        return None


class AtherTheftMovementSensor(AtherSensor):
    """Representation of the Theft Movement sensor."""

    _attr_name = "Theft Movement State"
    _attr_icon = "mdi:shield-alert"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_theft_movement"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("TheftTowMovementState")


class AtherAltitudeSensor(AtherSensor):
    """Representation of the Altitude sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Altitude"
    _attr_icon = "mdi:altimeter"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_altitude"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("altitude")
