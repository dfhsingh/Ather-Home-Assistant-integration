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
