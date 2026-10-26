"""Expose Vacuula robots in Home Assistant."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VacuulaClient
from .coordinator import VacuulaCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
type VacuulaConfigEntry = ConfigEntry[VacuulaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Connect to Vacuula and set up its sensors."""
    client = VacuulaClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = VacuulaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Unload the sensors and their coordinator listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
