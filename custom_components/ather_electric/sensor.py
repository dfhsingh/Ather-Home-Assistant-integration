"""Sensor platform for Ather Electric."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfSpeed
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from .const import DOMAIN
from .binary_sensor import is_binary_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ather Electric sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug(
        "Setting up Ather Sensors. Coordinator Data keys: %s",
        list(coordinator.data.keys()),
    )

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
        AtherModeRangeSensor(coordinator, "WarpPlus", "WarpPlusModeRange"),
        AtherVehicleStateSensor(coordinator),
        AtherChargerTypeSensor(coordinator),
        AtherSoftwareVersionSensor(coordinator),
        AtherSavingsSensor(coordinator),
        # Projected Ranges (Stats)
        AtherProjectedRangeSensor(coordinator, "Eco", "ecoModePredictedRange_kms"),
        AtherProjectedRangeSensor(coordinator, "Ride", "rideModePredictedRange_kms"),
        AtherProjectedRangeSensor(coordinator, "Sport", "sportModePredictedRange_kms"),
        AtherProjectedRangeSensor(coordinator, "Warp", "warpModePredictedRange_kms"),
        AtherProjectedRangeSensor(
            coordinator, "WarpPlus", "warpPlusModePredictedRange_kms"
        ),
        AtherProjectedRangeSensor(
            coordinator, "SmartEco", "smartEcoModePredictedRange_kms"
        ),
        AtherAltitudeSensor(coordinator),
        AtherTheftMovementSensor(coordinator),
        AtherSmartChargingSensor(coordinator),
        # New Sensors
        AtherTripDistanceSensor(coordinator, "A"),
        AtherTripDistanceSensor(coordinator, "B"),
        AtherTripEfficiencySensor(coordinator, "A"),
        AtherTripEfficiencySensor(coordinator, "B"),
        AtherTripAvgSpeedSensor(coordinator, "A"),
        AtherTripAvgSpeedSensor(coordinator, "B"),
        AtherSubscriptionStatusSensor(coordinator),
        AtherTimeRemainingSensor(coordinator, "full", "Time to Full Charge"),
        AtherTimeRemainingSensor(coordinator, "80", "Time to 80% Charge"),
        AtherServiceSensor(coordinator),
        AtherWarrantySensor(
            coordinator, "battery", "status", "Battery Warranty Status"
        ),
        AtherWarrantySensor(
            coordinator,
            "battery",
            "last_purchase_date",
            "Battery Warranty Date",
            SensorDeviceClass.TIMESTAMP,
        ),
        AtherWarrantySensor(
            coordinator, "vehicle", "status", "Vehicle Warranty Status"
        ),
        AtherWarrantySensor(
            coordinator,
            "vehicle",
            "last_purchase_date",
            "Vehicle Warranty Date",
            SensorDeviceClass.TIMESTAMP,
        ),
        # Current Trip Sensors
        AtherCurrentTripDistanceSensor(coordinator),
        AtherCurrentTripDurationSensor(coordinator),
        AtherCurrentTripSpeedSensor(coordinator),
        # Navigation & Subscription
        AtherSubscriptionExpirySensor(coordinator),
        AtherChargingCreditsSensor(coordinator),
        # Hardware Diagnostics
        AtherDiagnosticSensor(coordinator, "Motor Type", "motor_type", "mdi:engine"),
        AtherDiagnosticSensor(
            coordinator, "Controller Type", "controller_type", "mdi:cpu-64-bit"
        ),
        AtherDiagnosticSensor(
            coordinator, "Generation", "generation", "mdi:identifier"
        ),
        AtherDiagnosticSensor(coordinator, "City", "city", "mdi:city"),
        AtherRemoteShutdownSensor(coordinator),
    ]

    # Dynamic Non-Binary Feature Flags Discovery
    features = coordinator.get_data("features", {})
    if features:
        for feature_key, value in features.items():
            # Check if it looks like a NON-binary flag (values like 79, 110, etc.)
            if not is_binary_value(value):
                # Generate a readable name
                readable_name = (
                    feature_key.replace("_", " ")
                    .replace("app", "App")
                    .replace("vehicle", "Vehicle")
                    .replace("atherStack", "Ather Stack")
                )
                readable_name = " ".join(
                    word.capitalize() for word in readable_name.split()
                )
                
                entities.append(
                    AtherFeatureSensor(coordinator, feature_key, readable_name)
                )

    async_add_entities(entities)


class AtherSensor(SensorEntity):
    """Base class for Ather sensors."""

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

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        attrs = {}
        last_synced = self.coordinator.get_data("lastSyncedTime")
        if last_synced:
            try:
                # Convert ms to ISO string or datetime for HA
                from datetime import datetime, timezone

                if isinstance(last_synced, (int, float)):
                    val = datetime.fromtimestamp(last_synced / 1000, tz=timezone.utc)
                    attrs["last_synced_time"] = val
            except Exception:
                pass
        return attrs

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

    _attr_entity_registry_enabled_default = False

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
    _attr_icon = "mdi:moped-electric"

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

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

    _attr_entity_registry_enabled_default = False

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
        attrs = super().extra_state_attributes
        attrs.update(
            {
                "plan": self.coordinator.get_data("subscription_plan"),
            }
        )
        return attrs


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


class AtherVehicleStateSensor(AtherSensor):
    """Representation of the Vehicle State sensor."""

    _attr_name = "Vehicle State"
    _attr_icon = "mdi:moped-electric"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_vehicle_state"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.get_data("vehicleState")


class AtherChargerTypeSensor(AtherSensor):
    """Representation of Charger Type."""

    _attr_name = "Charger Type"
    _attr_icon = "mdi:ev-plug-type2"

    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_charger_type"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.get_data("chargerType")


class AtherSoftwareVersionSensor(AtherSensor):
    """Representation of User Facing Software Version."""

    _attr_name = "Software Version"
    _attr_icon = "mdi:cellphone-arrow-down"

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_sw_version"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.get_data("UserFacingSoftwareVersion")


class AtherSavingsSensor(AtherSensor):
    """Representation of Total Savings."""

    _attr_name = "Total Savings"
    _attr_native_unit_of_measurement = "INR"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_savings"

    @property
    def native_value(self) -> float | None:
        # Check 'app' -> 'savings' or 'savings' direct
        val = self.coordinator.get_data("app", {}).get("savings")
        if val is None:
            val = self.coordinator.get_data("savings")

        if val is not None:
            return round(float(val), 2)
        return None


class AtherRemoteShutdownSensor(AtherSensor):
    """Representation of Remote Shutdown Status."""

    _attr_name = "Remote Shutdown State"
    _attr_icon = "mdi:power-settings"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_remote_shutdown"

    @property
    def native_value(self) -> str | None:
        # Data: remote_shutdown -> state (0?)
        data = self.coordinator.get_data("remote_shutdown", {})
        state = data.get("state")
        if state is not None:
            # Map state logic if known. For now, returning raw state or simplified string
            # Assuming 0 = Inactive/Success?
            return str(state)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        attrs = super().extra_state_attributes
        data = self.coordinator.get_data("remote_shutdown", {})
        attrs.update(
            {
                "error": data.get("error"),
                "request_id": data.get("request_id"),
                "timestamp": data.get("timestamp"),
            }
        )
        return attrs


class AtherProjectedRangeSensor(AtherSensor):
    """Representation of Projected Range (Stats)."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, mode_name: str, key_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key_name = key_name
        self._attr_name = f"Projected Range ({mode_name})"
        self._id_suffix = mode_name.lower().replace(" ", "_")

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_proj_range_{self._id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        # Data is in tripSummary object
        trip_summary = self.coordinator.get_data("tripSummary", {})
        if trip_summary:
            return trip_summary.get(self._key_name)
        return None


class AtherSmartChargingSensor(AtherSensor):
    """Representation of Smart Charging Setting."""

    _attr_name = "Smart Charging Setting"
    _attr_icon = "mdi:battery-sync"
    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_smart_charging_setting"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        # charging -> SmartChargingSetting: "Off"
        charging = self.coordinator.get_data("charging", {})
        return charging.get("SmartChargingSetting")


class AtherServiceSensor(AtherSensor):
    """Representation of the Last Service Date sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last Service Date"
    _attr_icon = "mdi:calendar-check"
    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_last_service"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        service = self.coordinator.get_data("vehicle_service", {})
        ts_ms = service.get("time")  # String "1766582133967"

        if ts_ms and str(ts_ms).isdigit():
            try:
                from datetime import datetime, timezone

                # Log confirms ms timestamp
                return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
            except Exception:
                pass
        return None

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        attrs = super().extra_state_attributes
        service = self.coordinator.get_data("vehicle_service", {})
        attrs.update(
            {
                "advisor_contact": service.get("serviceAdvisorContactNumber"),
                "paid_amount": service.get("paidAmount"),
                "status": service.get("status"),
            }
        )
        return attrs


class AtherWarrantySensor(AtherSensor):
    """Representation of Warranty Information."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator, item: str, key: str, name: str, device_class=None
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.item = item  # "battery" or "vehicle"
        self.key = (
            key  # "status" (mapped from action?) or "last_purchase_date" or "action"
        )
        self._attr_name = name
        if device_class:
            self._attr_device_class = device_class

        # Unique ID needs to be unique per sensor
        self._id_suffix = f"{item}_{key}"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_warranty_{self._id_suffix}"

    @property
    def native_value(self) -> any:
        # Warranty data: warranty -> battery -> {action: 2, last_purchase_date: ...}
        warranty = self.coordinator.get_data("warranty", {})
        item_data = warranty.get(self.item, {})

        if self.key == "last_purchase_date":
            # "2025-11-18T11:38:11.000Z" -> ISO String, SensorDeviceClass.TIMESTAMP handles it if it's datetime obj or valid ISO string?
            # HA usually prefers datetime object
            date_str = item_data.get("last_purchase_date")
            if date_str:
                try:
                    from datetime import datetime

                    # It ends with Z, python fromisoformat might need handling for Z in older versions but HA python env handles it usually.
                    # Or replace Z with +00:00
                    if date_str.endswith("Z"):
                        date_str = date_str[:-1] + "+00:00"
                    return datetime.fromisoformat(date_str)
                except:
                    return date_str

        elif self.key == "status":
            # We saw "action": 2.  User asked "what are action codes?".
            # We don't know yet, so let's just return the raw action value or map it if we knew.
            # For now, let's look for "action"
            return item_data.get("action")

        return item_data.get(self.key)


class AtherCurrentTripSensor(AtherSensor):
    """Base class for Current Trip sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        # We need to distinguish these sensors
        # ID suffix will be set by subclasses

    @property
    def current_trip_data(self) -> dict:
        """Return current trip data."""
        return self.coordinator.get_data("current_trip", {})

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        attrs = super().extra_state_attributes
        data = self.current_trip_data
        if "timestamp" in data:
            # Add timestamp as attribute for tracking unique trips
            attrs["last_synced"] = data["timestamp"]
        return attrs


class AtherCurrentTripDistanceSensor(AtherCurrentTripSensor):
    """Representation of Current Trip Distance."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Current Trip Distance"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_current_trip_distance"

    @property
    def native_value(self) -> float | None:
        return self.current_trip_data.get("distance")


class AtherCurrentTripDurationSensor(AtherCurrentTripSensor):
    """Representation of Current Trip Duration."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"  # Seconds
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Current Trip Duration"
    _attr_icon = "mdi:timer"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_current_trip_duration"

    @property
    def native_value(self) -> int | None:
        return self.current_trip_data.get("time")


class AtherCurrentTripSpeedSensor(AtherCurrentTripSensor):
    """Representation of Current Trip Average Speed."""

    _attr_device_class = SensorDeviceClass.SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Current Trip Avg Speed"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_current_trip_avg_speed"

    @property
    def native_value(self) -> float | None:
        return self.current_trip_data.get("averageSpeed")





class AtherSubscriptionExpirySensor(AtherSensor):
    """Connect Subscription expiry date."""

    _attr_name = "Subscription Expiry"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-alert"

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_sub_expiry"

    @property
    def native_value(self):
        """Return expiry timestamp."""
        ts_ms = self.coordinator.get_data("subscription_end_at")
        if ts_ms and str(ts_ms).isdigit():
            from datetime import datetime, timezone

            return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        return None


class AtherChargingCreditsSensor(AtherSensor):
    """Available charging credits."""

    _attr_name = "Charging Credits"
    _attr_icon = "mdi:battery-plus-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_charging_credits"

    @property
    def native_value(self) -> int | None:
        features = self.coordinator.get_data("features", {})
        return features.get("chargingCreditsAvailable")


class AtherDiagnosticSensor(AtherSensor):
    """General diagnostic sensor for scooter properties."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, name: str, property_key: str, icon: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = name
        self._property_key = property_key
        self._attr_icon = icon

    @property
    def unique_id(self) -> str:
        return f"ather_{self.coordinator.scooter_id}_diag_{self._property_key}"

    @property
    def native_value(self):
        # Check in properties dict first
        props = self.coordinator.get_data("properties", {})
        val = props.get(self._property_key)
        if val is None:
            # Fallback to root (some like generation are root)
            val = self.coordinator.get_data(self._property_key)
        return val


class AtherFeatureSensor(AtherSensor):
    """Representation of a generic feature sensor (Diagnostic, Non-Binary)."""

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
    def native_value(self) -> any:
        """Return the state of the sensor."""
        features = self.coordinator.get_data("features", {})
        return features.get(self.feature_key)
