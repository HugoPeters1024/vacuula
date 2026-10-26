"""Poll the robot inventory and isolate failures to individual robots."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RobotStatus, VacuulaClient
from .const import DOMAIN, POLL_INTERVAL_SECONDS, ROBOT_COMMANDS

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RobotData:
    """The data shared by the robot sensors."""

    name: str
    robot_type: str
    status: RobotStatus


class VacuulaCoordinator(DataUpdateCoordinator[dict[str, RobotData]]):
    """Share one polling cycle between the sensors."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VacuulaClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, RobotData]:
        try:
            robots = await self.client.async_get_robots()
        except (ClientError, TimeoutError, ValueError) as err:
            raise UpdateFailed(f"Cannot fetch Vacuula robots: {err}") from err

        async def fetch(serial: str, robot: dict) -> tuple[str, RobotData]:
            status = RobotStatus()
            if robot["connected"]:
                try:
                    status = await self.client.async_get_status(serial, robot["type"])
                except (ClientError, TimeoutError, ValueError) as err:
                    _LOGGER.debug("Cannot read status for %s: %s", serial, err)
            return serial, RobotData(robot["name"], robot["type"], status)

        # A slow robot must not delay requests to the other robots.
        return dict(
            await asyncio.gather(
                *(
                    fetch(serial, robot)
                    for serial, robot in robots.items()
                    if robot["type"] in ROBOT_COMMANDS
                )
            )
        )
