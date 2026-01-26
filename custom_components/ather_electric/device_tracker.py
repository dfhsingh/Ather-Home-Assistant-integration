"""Device tracker for Ather Electric."""

from __future__ import annotations

import logging
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ather device tracker."""
    _LOGGER.info("Setting up Ather Device Tracker platform")
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AtherTracker(coordinator)])


class AtherTracker(TrackerEntity):
    """Represent the scooter's location."""

    def __init__(self, coordinator) -> None:
        """Initialize the tracker."""
        self.coordinator = coordinator
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"ather_{coordinator.scooter_id}_location"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.scooter_id)},
            name=coordinator.device_name,
            manufacturer="Ather Energy",
            model=coordinator.get_data("model_type") or "450X",
            hw_version=coordinator.get_data("model"),
            sw_version=f"{coordinator.get_data('UserFacingSoftwareVersion')} (v{coordinator.integration_version})",
        )
        self._attr_entity_category = None
        _LOGGER.debug("AtherTracker initialized for %s", coordinator.scooter_id)

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.coordinator.async_add_listener(self.async_write_ha_state)
        _LOGGER.debug("AtherTracker added to HASS")

    @property
    def source_type(self) -> SourceType:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        # Check various possible keys
        val = self.coordinator.get_data("gpsLat") or self.coordinator.get_data("lat")
        if val:
            pass
            # _LOGGER.debug("Got latitude: %s", val)
        else:
            _LOGGER.debug("Latitude is None")
        return float(val) if val else None

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        val = self.coordinator.get_data("gpsLon") or self.coordinator.get_data("lon")
        if val:
            pass
            # _LOGGER.debug("Got longitude: %s", val)
        return float(val) if val else None

    @property
    def gps_accuracy(self) -> int | None:
        """Return the gps accuracy of the device."""
        return self.coordinator.get_data("gps_accuracy")

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the device."""
        return self.coordinator.get_data("batterySOC")

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return device capability attributes."""
        attrs = {}
        accuracy = self.coordinator.get_data("gps_accuracy")
        if accuracy:
            attrs["gps_accuracy"] = accuracy

        # Live Location Sharing & Emergency Contacts
        sharing = self.coordinator.get_data("live_location_sharing", {})
        if sharing:
            attrs["auto_share_enabled"] = sharing.get("automatic_share_enabled")
            contacts = sharing.get("emergency_contacts", {})
            if isinstance(contacts, dict):
                attrs["emergency_contacts"] = [
                    {"name": c.get("name"), "number": c.get("number")}
                    for c in contacts.values()
                    if isinstance(c, dict)
                ]

        return attrs
