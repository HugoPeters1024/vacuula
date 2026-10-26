"""Charging, docked, and problem sensors for Vacuula robots."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity

PARALLEL_UPDATES = 0
DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    BinarySensorEntityDescription(
        key="docked", translation_key="docked", icon="mdi:ev-station"
    ),
    BinarySensorEntityDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors, including those for robots paired after setup."""
    coordinator = entry.runtime_data
    known_serials: set[str] = set()

    @callback
    def add_new_robots() -> None:
        new_serials = coordinator.data.keys() - known_serials
        known_serials.update(new_serials)
        async_add_entities(
            VacuulaBinarySensor(coordinator, serial, description)
            for serial in new_serials
            for description in DESCRIPTIONS
        )

    add_new_robots()
    entry.async_on_unload(coordinator.async_add_listener(add_new_robots))


class VacuulaBinarySensor(VacuulaEntity, BinarySensorEntity):
    """One boolean reading from the shared status response."""

    def __init__(
        self,
        coordinator: VacuulaCoordinator,
        serial: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        robot = self.coordinator.data.get(self.serial)
        return getattr(robot.status, self.entity_description.key) if robot else None

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self) -> dict[str, list[str]] | None:
        if self.entity_description.key != "problem":
            return None
        robot = self.coordinator.data.get(self.serial)
        return {"error_codes": list(robot.status.error_codes) if robot else []}
