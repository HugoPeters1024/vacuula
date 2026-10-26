"""Exercise the integration through Home Assistant and its HTTP client."""

from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientConnectionError
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_URL, STATE_UNAVAILABLE
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.api import (
    RobotStatus,
    VacuulaClient,
    normalize_url,
    parse_status,
)
from custom_components.vacuula.const import DOMAIN

URL = "http://vacuula.local"
ROBOTS = {
    "gen3-serial": {"name": "Upstairs", "type": "neato.gen3", "connected": True},
    "gen4serial": {"name": "Downstairs", "type": "neato.gen4", "connected": True},
}


@pytest.mark.parametrize(
    "url",
    [
        "vacuula.local",
        "ftp://host",
        "http://u:p@host",
        "http://host?q=1",
        "http://host/#fragment",
    ],
)
def test_invalid_url(url):
    with pytest.raises(ValueError):
        normalize_url(url)


def test_normalize_url():
    assert normalize_url(" HTTP://VACUULA.local:80/ ") == URL


@pytest.mark.parametrize(
    ("robot_type", "payload", "command", "expected"),
    [
        ("neato.gen3", {"details": {"charge": 0}}, {"cmd": "getRobotState"}, 0),
        (
            "neato.gen4",
            {"body": {"details": {"charge": 100}}},
            {"ability": "state.show"},
            100,
        ),
    ],
)
async def test_battery_api(
    hass, aioclient_mock, robot_type, payload, command, expected
):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post(f"{URL}/api/robot/serial/command", json=payload)
    client = VacuulaClient(async_get_clientsession(hass), URL)
    assert (await client.async_get_status("serial", robot_type)).battery == expected
    assert aioclient_mock.mock_calls[-1][2] == command


@pytest.mark.parametrize(
    "charge", [None, True, "50", -1, 101, float("nan"), float("inf")]
)
async def test_invalid_battery(hass, aioclient_mock, charge):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post(
        f"{URL}/api/robot/serial/command", json={"details": {"charge": charge}}
    )
    client = VacuulaClient(async_get_clientsession(hass), URL)
    assert (await client.async_get_status("serial", "neato.gen3")).battery is None


async def test_config_flow(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/robots", json=ROBOTS)
    with patch("custom_components.vacuula.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: URL + "/"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == {CONF_URL: URL}
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_URL: URL}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("url", "response", "error"),
    [("bad", None, {CONF_URL: "invalid_url"}), (URL, [], {"base": "cannot_connect"})],
)
async def test_config_errors(hass, aioclient_mock, url, response, error):
    aioclient_mock.get(f"{URL}/api/robots", json=response)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_URL: url}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == error


async def test_sensors_lifecycle(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL})
    entry.add_to_hass(hass)
    robots = {serial: dict(robot) for serial, robot in ROBOTS.items()}
    with (
        patch.object(
            VacuulaClient, "async_get_robots", AsyncMock(return_value=robots)
        ) as inventory,
        patch.object(
            VacuulaClient,
            "async_get_status",
            AsyncMock(return_value=RobotStatus(42, False, True, False)),
        ) as battery,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, "gen3-serial_battery"
        )
        other_id = registry.async_get_entity_id("sensor", DOMAIN, "gen4serial_battery")
        state = hass.states.get(entity_id)
        assert state.state == "42"
        assert state.attributes["device_class"] == "battery"
        assert state.attributes["unit_of_measurement"] == "%"
        assert state.attributes["state_class"] == "measurement"
        device = dr.async_get(hass).async_get_device(
            identifiers={(DOMAIN, "gen3-serial")}
        )
        assert device.name == "Upstairs"

        # A disconnected robot must not receive commands or keep an old reading.
        robots["gen3-serial"]["connected"] = False
        battery.reset_mock()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
        assert hass.states.get(other_id).state == "42"
        battery.assert_awaited_once_with("gen4serial", "neato.gen4")

        # A command timeout affects only that robot, then recovers on the next poll.
        robots["gen3-serial"]["connected"] = True

        async def read_battery(serial, robot_type):
            if serial == "gen3-serial":
                raise TimeoutError
            return RobotStatus(0, False, True, False)

        battery.side_effect = read_battery
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
        assert hass.states.get(other_id).state == "0"
        battery.side_effect = None
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "42"

        # Newly paired robots appear without an integration reload.
        robots["new"] = {"name": "New robot", "type": "neato.gen3", "connected": True}
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        new_id = registry.async_get_entity_id("sensor", DOMAIN, "new_battery")
        assert hass.states.get(new_id).state == "42"

        inventory.side_effect = ClientConnectionError
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
        assert hass.states.get(other_id).state == STATE_UNAVAILABLE
        inventory.side_effect = None
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(other_id).state == "42"

        coordinator = entry.runtime_data
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert not list(coordinator.async_contexts())


async def test_setup_retries_unavailable_server(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL})
    entry.add_to_hass(hass)
    with patch.object(
        VacuulaClient, "async_get_robots", side_effect=ClientConnectionError
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("payload", [{}, {"details": None}, {"details": []}])
async def test_missing_battery_details(hass, aioclient_mock, payload):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post(f"{URL}/api/robot/serial/command", json=payload)
    client = VacuulaClient(async_get_clientsession(hass), URL)
    assert (await client.async_get_status("serial", "neato.gen3")).battery is None


async def test_config_connection_error(hass):
    with patch.object(
        VacuulaClient, "async_get_robots", side_effect=ClientConnectionError
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_URL: URL}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_initially_empty_server(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL})
    entry.add_to_hass(hass)
    with (
        patch.object(VacuulaClient, "async_get_robots", return_value={}) as inventory,
        patch.object(
            VacuulaClient, "async_get_status", return_value=RobotStatus(battery=75)
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        inventory.return_value = ROBOTS
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, "gen3-serial_battery"
        )
        assert hass.states.get(entity_id).state == "75"
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert (
            registry.async_get_entity_id("sensor", DOMAIN, "gen3-serial_battery")
            == entity_id
        )
        assert hass.states.get(entity_id).state == "75"


@pytest.mark.parametrize(
    ("robot_type", "data", "expected", "codes"),
    [
        ("neato.gen3", {"error": None, "alert": None}, False, ()),
        (
            "neato.gen3",
            {"error": "dustbin_missing", "alert": None},
            True,
            ("dustbin_missing",),
        ),
        (
            "neato.gen3",
            {"error": None, "alert": "dustbin_full"},
            True,
            ("dustbin_full",),
        ),
        ("neato.gen3", {"state": 4}, True, ()),
        ("neato.gen3", {}, None, ()),
        ("neato.gen3", {"error": [], "alert": None}, None, ()),
        ("neato.gen4", {"errors": None}, False, ()),
        ("neato.gen4", {"errors": []}, False, ()),
        (
            "neato.gen4",
            {"errors": [{"code": "lw_hanging", "severity": "error"}]},
            True,
            ("lw_hanging",),
        ),
        (
            "neato.gen4",
            {"errors": [{"code": "test_warning", "severity": "warning"}]},
            True,
            ("test_warning",),
        ),
        ("neato.gen4", {"state": "error", "errors": []}, True, ()),
        ("neato.gen4", {}, None, ()),
        ("neato.gen4", {"errors": "invalid"}, None, ()),
        ("neato.gen4", {"errors": [{}]}, None, ()),
    ],
)
def test_problem_mapping(robot_type, data, expected, codes):
    status = parse_status(data, robot_type)
    assert status.problem is expected
    assert status.error_codes == codes


@pytest.mark.parametrize("robot_type", ["neato.gen3", "neato.gen4"])
async def test_binary_sensors(hass, aioclient_mock, robot_type):
    """All four sensors share a request and recover independently from bad fields."""
    serial = "test-robot"
    robots = {serial: {"name": "Neato", "type": robot_type, "connected": True}}
    gen3 = robot_type == "neato.gen3"
    details = {
        "charge": 97,
        "isCharging" if gen3 else "is_charging": False,
        "isDocked" if gen3 else "is_docked": True,
    }
    status = {
        "details": details,
        **({"error": None, "alert": None} if gen3 else {"errors": []}),
    }
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL})
    entry.add_to_hass(hass)

    def responses():
        aioclient_mock.clear_requests()
        aioclient_mock.get(f"{URL}/api/robots", json=robots)
        aioclient_mock.post(
            f"{URL}/api/robot/{serial}/command",
            json=status if gen3 else {"body": status},
        )

    responses()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    ids = {
        key: registry.async_get_entity_id("binary_sensor", DOMAIN, f"{serial}_{key}")
        for key in ("charging", "docked", "problem")
    }
    battery_id = registry.async_get_entity_id("sensor", DOMAIN, f"{serial}_battery")
    assert len(aioclient_mock.mock_calls) == 2
    assert hass.states.get(ids["charging"]).state == "off"
    assert hass.states.get(ids["docked"]).state == "on"
    assert hass.states.get(ids["problem"]).state == "off"
    assert (
        hass.states.get(ids["charging"]).attributes["device_class"]
        == "battery_charging"
    )
    assert hass.states.get(ids["problem"]).attributes["device_class"] == "problem"
    assert all(
        registry.async_get(eid).device_id == registry.async_get(battery_id).device_id
        for eid in ids.values()
    )

    # Invalid values must not become False or invalidate unrelated fields.
    details["charge"] = -1
    details["isCharging" if gen3 else "is_charging"] = "false"
    if gen3:
        status["error"] = "dustbin_missing"
    else:
        status["errors"] = [{"code": "dustbin_missing", "severity": "error"}]
    responses()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(battery_id).state == STATE_UNAVAILABLE
    assert hass.states.get(ids["charging"]).state == STATE_UNAVAILABLE
    assert hass.states.get(ids["docked"]).state == "on"
    assert hass.states.get(ids["problem"]).state == "on"
    assert hass.states.get(ids["problem"]).attributes["error_codes"] == [
        "dustbin_missing"
    ]

    robots[serial]["connected"] = False
    responses()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(aioclient_mock.mock_calls) == 1
    assert all(hass.states.get(eid).state == STATE_UNAVAILABLE for eid in ids.values())

    robots[serial]["connected"] = True
    details["charge"] = 98
    details["isCharging" if gen3 else "is_charging"] = True
    if gen3:
        status["error"] = None
    else:
        status["errors"] = None
    responses()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(battery_id).state == "98"
    assert hass.states.get(ids["charging"]).state == "on"
    assert hass.states.get(ids["problem"]).state == "off"
    assert hass.states.get(ids["problem"]).attributes["error_codes"] == []
