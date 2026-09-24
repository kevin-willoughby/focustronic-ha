"""Config flow: log in, then auto-discover the Alkatronic device(s) on the account."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .api import AlkatronicApiError, AlkatronicAuthError, AlkatronicClient
from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_DOSETRONIC_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class AlkatronicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the setup UI: credentials, then device auto-discovery."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._client: AlkatronicClient | None = None
        self._alkatronic_devices: list[dict[str, Any]] = []
        self._dosetronic_devices: list[dict[str, Any]] = []
        self._dosetronic_id: str | None = None
        self._chosen_alkatronic: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            # device_id isn't known yet — the client only needs it for the
            # records endpoint, which we don't call during setup.
            client = AlkatronicClient(
                session, user_input[CONF_EMAIL], user_input[CONF_PASSWORD], ""
            )
            try:
                await client.async_login()
                devices_by_type = await client.async_get_devices()
            except AlkatronicAuthError:
                errors["base"] = "invalid_auth"
            except (AlkatronicApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            else:
                alkatronic_devices = devices_by_type.get("alkatronic", [])
                if not alkatronic_devices:
                    errors["base"] = "no_devices"
                else:
                    self._email = user_input[CONF_EMAIL]
                    self._password = user_input[CONF_PASSWORD]
                    self._client = client
                    self._alkatronic_devices = alkatronic_devices
                    # Dosetronic is optional — linking one lets us also expose
                    # its pump sensors on this entry.
                    self._dosetronic_devices = devices_by_type.get("dosetronic", [])

                    if len(alkatronic_devices) == 1:
                        return await self._async_alkatronic_chosen(
                            alkatronic_devices[0]
                        )
                    return await self.async_step_select_device()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Only reached if the account has more than one Alkatronic device."""
        options = {
            str(device["id"]): device.get("friendly_name") or device["serial_number"]
            for device in self._alkatronic_devices
        }

        if user_input is not None:
            chosen_id = user_input[CONF_DEVICE_ID]
            device = next(
                d for d in self._alkatronic_devices if str(d["id"]) == chosen_id
            )
            return await self._async_alkatronic_chosen(device)

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": key, "label": label}
                            for key, label in options.items()
                        ]
                    )
                )
            }
        )
        return self.async_show_form(step_id="select_device", data_schema=schema)

    async def _async_alkatronic_chosen(
        self, device: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Called once the Alkatronic device for this entry is settled."""
        self._chosen_alkatronic = device

        if not self._dosetronic_devices:
            return await self._async_create(device)
        if len(self._dosetronic_devices) == 1:
            self._dosetronic_id = str(self._dosetronic_devices[0]["id"])
            return await self._async_create(device)
        return await self.async_step_select_dosetronic()

    async def async_step_select_dosetronic(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Only reached if the account has more than one Dosetronic device."""
        options = {
            str(device["id"]): device.get("friendly_name") or device["serial_number"]
            for device in self._dosetronic_devices
        }
        none_value = "__none__"

        if user_input is not None:
            chosen_id = user_input[CONF_DOSETRONIC_ID]
            if chosen_id != none_value:
                self._dosetronic_id = chosen_id
            return await self._async_create(self._chosen_alkatronic)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DOSETRONIC_ID, default=none_value
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": none_value, "label": "None"}]
                        + [
                            {"value": key, "label": label}
                            for key, label in options.items()
                        ]
                    )
                )
            }
        )
        return self.async_show_form(step_id="select_dosetronic", data_schema=schema)

    async def _async_create(
        self, device: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        device_id = str(device["id"])
        device_name = device.get("friendly_name") or device["serial_number"]

        await self.async_set_unique_id(f"{self._email}_{device_id}")
        self._abort_if_unique_id_configured()

        data = {
            CONF_EMAIL: self._email,
            CONF_PASSWORD: self._password,
            CONF_DEVICE_ID: device_id,
            CONF_DEVICE_NAME: device_name,
        }
        if self._dosetronic_id:
            data[CONF_DOSETRONIC_ID] = self._dosetronic_id

        return self.async_create_entry(title=f"Alkatronic ({device_name})", data=data)
