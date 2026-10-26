"""Battery sensors for Vacuula robots."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for existing robots and robots paired later."""
    coordinator = entry.runtime_data
    known_serials: set[str] = set()

    @callback
    def add_new_robots() -> None:
        new_serials = coordinator.data.keys() - known_serials
        known_serials.update(new_serials)
        async_add_entities(
            VacuulaBatterySensor(coordinator, serial) for serial in new_serials
        )

    add_new_robots()
    entry.async_on_unload(coordinator.async_add_listener(add_new_robots))


class VacuulaBatterySensor(VacuulaEntity, SensorEntity):
    """A robot's battery percentage, identified by its stable serial number."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_battery"

    @property
    def available(self) -> bool:
        """Do not show a stale reading after a server or robot failure."""
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> int | float | None:
        """Return the latest battery reading."""
        robot = self.coordinator.data.get(self.serial)
        return robot.status.battery if robot else None
