"""Button platform for Alkatronic — trigger an on-demand extra measurement."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    records_coordinator = coordinators["records"]
    status_coordinator = coordinators["status"]

    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Alkatronic")

    async_add_entities(
        [
            AlkatronicExtraMeasurementButton(
                records_coordinator, status_coordinator, device_id, device_name
            )
        ]
    )


class AlkatronicExtraMeasurementButton(ButtonEntity):
    """Triggers an extra measurement on the Alkatronic device."""

    _attr_has_entity_name = True
    _attr_name = "Extra Measurement"

    def __init__(
        self, records_coordinator, status_coordinator, device_id: str, device_name: str
    ) -> None:
        self._records_coordinator = records_coordinator
        self._status_coordinator = status_coordinator
        self._attr_unique_id = f"{device_id}_extra_measurement"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Focustronic",
            model="Alkatronic",
        )

    async def async_press(self) -> None:
        await self._records_coordinator.client.async_schedule_test()
        # The new test result isn't available immediately — the device still
        # has to run it — so just nudge the status coordinator (next_test_time
        # etc.) rather than expecting fresh records right away.
        await self._status_coordinator.async_request_refresh()
