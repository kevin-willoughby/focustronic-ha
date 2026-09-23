"""The Alkatronic integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AlkatronicClient
from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import AlkatronicCoordinator, AlkatronicDeviceStatusCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = AlkatronicClient(
        session,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_DEVICE_ID],
    )

    records_coordinator = AlkatronicCoordinator(hass, client)
    status_coordinator = AlkatronicDeviceStatusCoordinator(hass, client)

    await records_coordinator.async_config_entry_first_refresh()
    await status_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "records": records_coordinator,
        "status": status_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
