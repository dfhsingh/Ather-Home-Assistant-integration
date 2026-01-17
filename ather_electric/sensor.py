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
        # New Sensors
        AtherTripDistanceSensor(coordinator, "A"),
        AtherTripDistanceSensor(coordinator, "B"),
        AtherTripEfficiencySensor(coordinator, "A"),
        AtherTripEfficiencySensor(coordinator, "B"),
        AtherTripAvgSpeedSensor(coordinator, "A"),
        AtherTripAvgSpeedSensor(coordinator, "B"),
        AtherNavigationStateSensor(coordinator),
        AtherSubscriptionStatusSensor(coordinator),
        AtherTimeRemainingSensor(coordinator, "full", "Time to Full Charge"),
        AtherTimeRemainingSensor(coordinator, "80", "Time to 80% Charge"),
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
        val = self.coordinator.get_data("altitude")
        if val is not None:
            return round(float(val), 2)
        return None


class AtherTripDistanceSensor(AtherSensor):
    """Representation of Trip Distance."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, trip_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.trip_id = trip_id
        self._attr_name = f"Trip {trip_id} Distance"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_trip_{self.trip_id}_distance"

    @property
    def native_value(self) -> float | None:
        key = f"trip{self.trip_id}"
        data = self.coordinator.get_data(key, {})
        return data.get("distance")


class AtherTripEfficiencySensor(AtherSensor):
    """Representation of Trip Efficiency."""

    _attr_name = "Trip Efficiency"
    _attr_native_unit_of_measurement = "km/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, trip_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.trip_id = trip_id
        self._attr_name = f"Trip {trip_id} Efficiency"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_trip_{self.trip_id}_efficiency"

    @property
    def native_value(self) -> float | None:
        key = f"trip{self.trip_id}"
        data = self.coordinator.get_data(key, {})
        val = data.get("efficiency")
        if val:
            try:
                wh_km = float(val)
                if wh_km > 0:
                    # Convert Wh/km to km/kWh
                    # 1 kWh = 1000 Wh
                    # km/kWh = 1000 / (Wh/km)
                    return round(1000 / wh_km, 2)
            except (ValueError, TypeError):
                pass
        return None


class AtherTripAvgSpeedSensor(AtherSensor):
    """Representation of Trip Average Speed."""

    _attr_device_class = SensorDeviceClass.SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, trip_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.trip_id = trip_id
        self._attr_name = f"Trip {trip_id} Avg Speed"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_trip_{self.trip_id}_avg_speed"

    @property
    def native_value(self) -> float | None:
        key = f"trip{self.trip_id}"
        data = self.coordinator.get_data(key, {})
        return data.get("avgSpeed")


class AtherNavigationStateSensor(AtherSensor):
    """Representation of Navigation State."""

    _attr_name = "Navigation Status"
    _attr_icon = "mdi:map-marker-path"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_nav_status"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.get_data("navigation_status")

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        return {
            "destination": self.coordinator.get_data("navigation_title"),
        }


class AtherSubscriptionStatusSensor(AtherSensor):
    """Representation of Subscription Status."""

    _attr_name = "Subscription Status"
    _attr_icon = "mdi:certificate"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_sub_status"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.get_data("subscription_status")

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        return {
            "plan": self.coordinator.get_data("subscription_plan"),
        }


class AtherTimeRemainingSensor(AtherSensor):
    """Representation of Time Remaining to Charge."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:battery-clock"

    def __init__(self, coordinator, charge_type: str, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.charge_type = charge_type  # "full" or "80"
        self._attr_name = name

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_time_to_{self.charge_type}"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        # charging data is updated in coordinator as a dict
        charging_data = self.coordinator.get_data("charging", {})
        ts_utc_str = None

        if self.charge_type == "full":
            ts_utc_str = charging_data.get("time2FullChargeUTC")
        elif self.charge_type == "80":
            ts_utc_str = charging_data.get("time2EightyChargeUTC")

        if ts_utc_str and str(ts_utc_str).isdigit():
            try:
                from datetime import datetime, timezone

                # Log says these are seconds.
                return datetime.fromtimestamp(int(ts_utc_str), tz=timezone.utc)
            except Exception:
                pass
        return None
