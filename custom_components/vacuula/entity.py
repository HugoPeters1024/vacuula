"""Shared robot identity for all Vacuula entities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VacuulaCoordinator


class VacuulaEntity(CoordinatorEntity[VacuulaCoordinator]):
    """Associate each entity with its physical robot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        super().__init__(coordinator, context=serial)
        self.serial = serial
        robot = coordinator.data[serial]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=robot.name,
            manufacturer="Neato",
            model=robot.robot_type,
            serial_number=serial,
            configuration_url=coordinator.client.base_url,
        )
