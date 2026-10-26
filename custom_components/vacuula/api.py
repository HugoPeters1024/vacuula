"""Small asynchronous client for the existing Vacuula HTTP API."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout
from yarl import URL

from .const import ROBOT_COMMANDS


def normalize_url(value: str) -> str:
    """Accept a server URL, without credentials, query parameters or a fragment."""
    url = URL(value.strip())
    if (
        url.scheme not in ("http", "https")
        or not url.host
        or url.user is not None
        or url.query_string
        or url.fragment
    ):
        raise ValueError("Enter the Vacuula server's HTTP or HTTPS URL")
    # Accessing port also validates the supplied port number.
    _ = url.port
    return str(url).rstrip("/")


@dataclass(frozen=True)
class RobotStatus:
    """Normalized readings; missing or invalid fields remain unavailable."""

    battery: int | float | None = None
    charging: bool | None = None
    docked: bool | None = None
    problem: bool | None = None
    error_codes: tuple[str, ...] = ()


def parse_status(data: dict[str, Any], robot_type: str) -> RobotStatus:
    """Normalize generation-specific fields without assuming missing values are off."""
    details = data.get("details")
    if not isinstance(details, dict):
        details = {}
    battery = details.get("charge")
    if type(battery) not in (int, float) or not 0 <= battery <= 100:
        battery = None
    gen3 = robot_type == "neato.gen3"
    charging = details.get("isCharging" if gen3 else "is_charging")
    docked = details.get("isDocked" if gen3 else "is_docked")
    problem = None
    codes: tuple[str, ...] = ()
    if gen3:
        reports = [data.get("error"), data.get("alert")]
        codes = tuple(value for value in reports if isinstance(value, str) and value)
        if all(key in data for key in ("error", "alert")) and all(
            value is None or isinstance(value, str) for value in reports
        ):
            problem = bool(codes)
        if codes or data.get("state") == 4:
            problem = True
    else:
        errors = data.get("errors")
        if "errors" in data and errors is None:
            problem = False
        elif isinstance(errors, list) and all(
            isinstance(error, dict) and isinstance(error.get("code"), str)
            for error in errors
        ):
            codes = tuple(error["code"] for error in errors)
            problem = bool(errors)
        if data.get("state") == "error":
            problem = True
    return RobotStatus(
        battery=battery,
        charging=charging if isinstance(charging, bool) else None,
        docked=docked if isinstance(docked, bool) else None,
        problem=problem,
        error_codes=codes,
    )


class VacuulaClient:
    """Use Home Assistant's shared HTTP session."""

    def __init__(self, session: ClientSession, base_url: str) -> None:
        self.session = session
        self.base_url = base_url

    async def _request(
        self, method: str, path: str, command: dict[str, str] | None = None
    ) -> dict[str, Any]:
        # The server waits up to 30 seconds for a robot command.
        async with self.session.request(
            method,
            f"{self.base_url}/api/{path}",
            json=command,
            timeout=ClientTimeout(total=35),
        ) as response:
            response.raise_for_status()
            data = await response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid Vacuula response")
        return data

    async def async_get_robots(self) -> dict[str, dict[str, Any]]:
        """Return the robot inventory, including disconnected robots."""
        robots = await self._request("GET", "robots")
        for robot in robots.values():
            if (
                not isinstance(robot, dict)
                or not isinstance(robot.get("type"), str)
                or not isinstance(robot.get("name"), str)
                or not isinstance(robot.get("connected"), bool)
            ):
                raise ValueError("Invalid Vacuula robot inventory")
        return robots

    async def async_get_status(self, serial: str, robot_type: str) -> RobotStatus:
        """Read all sensor values with one command per robot."""
        data = await self._request(
            "POST",
            f"robot/{quote(serial, safe='')}/command",
            ROBOT_COMMANDS[robot_type],
        )
        if robot_type == "neato.gen4":
            data = data.get("body")
        if not isinstance(data, dict):
            raise ValueError("Invalid robot status response")
        return parse_status(data, robot_type)
