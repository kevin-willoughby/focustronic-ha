"""Coordinator: polls the Alkatronic API on a schedule and shares the result."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AlkatronicApiError, AlkatronicAuthError, AlkatronicClient
from .const import (
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEVICE_STATUS_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AlkatronicCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetches records and exposes them (newest first) to all entities."""

    def __init__(self, hass: HomeAssistant, client: AlkatronicClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )
        self.client = client

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return await self.client.async_get_records()
        except AlkatronicAuthError as err:
            # Surfaces as a reauth flow rather than a silently-dead sensor.
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except AlkatronicApiError as err:
            raise UpdateFailed(f"Error communicating with Alkatronic: {err}") from err

    @property
    def latest(self) -> dict[str, Any] | None:
        """Convenience accessor for the most recent record."""
        return self.data[0] if self.data else None


class AlkatronicDeviceStatusCoordinator(
    DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]
):
    """Polls the account-wide device list — settings, pump levels, online status."""

    def __init__(self, hass: HomeAssistant, client: AlkatronicClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_status",
            update_interval=timedelta(minutes=DEVICE_STATUS_UPDATE_INTERVAL_MINUTES),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        try:
            return await self.client.async_get_devices()
        except AlkatronicAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except AlkatronicApiError as err:
            raise UpdateFailed(f"Error communicating with Alkatronic: {err}") from err
