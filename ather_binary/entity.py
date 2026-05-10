"""Base entity class for Ather Electric integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


class AtherEntity(CoordinatorEntity):
    """Base class for Ather entities."""

    def __init__(self, coordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
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
    def available(self) -> bool:
        """Return True if entity is available."""
        # Sensors retain value if we have data, even if disconnected
        return self.coordinator.last_update_success or bool(self.coordinator.data)

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
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
