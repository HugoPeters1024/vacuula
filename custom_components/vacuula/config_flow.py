"""Configure a Vacuula server through the Home Assistant UI."""

from typing import Any

import voluptuous as vol
from aiohttp import ClientError
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VacuulaClient, normalize_url
from .const import DOMAIN


class VacuulaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect to a user-supplied Vacuula server URL."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate the URL and server before creating an entry."""
        errors = {}
        if user_input is not None:
            try:
                url = normalize_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                self._async_abort_entries_match({CONF_URL: url})
                client = VacuulaClient(async_get_clientsession(self.hass), url)
                try:
                    await client.async_get_robots()
                except (ClientError, TimeoutError, ValueError):
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title="Vacuula", data={CONF_URL: url}
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL): str}),
            errors=errors,
        )
