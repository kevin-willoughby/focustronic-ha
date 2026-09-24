"""Thin async client for the (unofficial) Alkatronic cloud API."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    DEFAULT_HISTORY_DAYS,
    DEVICES_ENDPOINT,
    LOGIN_ENDPOINT,
    RECORDS_ENDPOINT,
    SCHEDULE_TEST_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


class AlkatronicAuthError(Exception):
    """Raised when login fails (bad credentials)."""


class AlkatronicApiError(Exception):
    """Raised for any other API failure."""


class AlkatronicClient:
    """Handles auth + data fetching for one Alkatronic account/device."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        device_id: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._device_id = device_id
        self._token: str | None = None

    async def async_login(self) -> None:
        """Log in and cache the token. Raises AlkatronicAuthError on bad creds."""
        payload = {
            "email": self._email,
            "password": self._password,
            "platform": "web",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
            }
        )

        async with self._session.post(
            LOGIN_ENDPOINT, data=payload, headers=headers
        ) as resp:
            if resp.status in (401, 403):
                raise AlkatronicAuthError("Invalid Alkatronic credentials")
            if resp.status != 200:
                raise AlkatronicApiError(f"Login failed: HTTP {resp.status}")

            body = await resp.json()
            token = body.get("data")
            if not token:
                raise AlkatronicAuthError("Login succeeded but no token returned")
            self._token = token

    async def async_get_devices(self) -> dict[str, list[dict[str, Any]]]:
        """Return devices grouped by type, e.g. {"alkatronic": [...], "dosetronic": [...]}.

        Only groups with at least one device are included, and each group's
        list contains only devices that were actually returned (empty groups
        from the API, like "mastertronic": [], are dropped).
        """
        if self._token is None:
            await self.async_login()

        devices = await self._fetch_devices()
        if devices is None:
            await self.async_login()
            devices = await self._fetch_devices()
            if devices is None:
                raise AlkatronicApiError("Failed to fetch devices after re-auth")

        return {
            group["type"]: group["devices"]
            for group in devices
            if group.get("devices")
        }

    async def _fetch_devices(self) -> list[dict[str, Any]] | None:
        params = {"token": self._token}
        async with self._session.get(DEVICES_ENDPOINT, params=params) as resp:
            if resp.status in (401, 403):
                return None
            if resp.status != 200:
                raise AlkatronicApiError(f"Device list fetch failed: HTTP {resp.status}")

            body = await resp.json()
            if not body.get("result"):
                raise AlkatronicApiError(
                    f"API returned failure: {body.get('message')}"
                )
            return body.get("data", [])

    async def async_get_records(
        self, days: int = DEFAULT_HISTORY_DAYS
    ) -> list[dict[str, Any]]:
        """Return the list of records, newest first. Logs in first if needed."""
        if self._token is None:
            await self.async_login()

        records = await self._fetch_records(days)
        if records is None:
            # Token likely expired — retry once after a fresh login.
            await self.async_login()
            records = await self._fetch_records(days)
            if records is None:
                raise AlkatronicApiError("Failed to fetch records after re-auth")

        # API returns oldest-first; we want newest-first for easy [0] access.
        return list(reversed(records))

    async def async_schedule_test(self) -> None:
        """Trigger an extra (on-demand) measurement on the device."""
        if self._token is None:
            await self.async_login()

        scheduled = await self._schedule_test()
        if not scheduled:
            await self.async_login()
            scheduled = await self._schedule_test()
            if not scheduled:
                raise AlkatronicApiError("Failed to schedule test after re-auth")

    async def _schedule_test(self) -> bool | None:
        url = SCHEDULE_TEST_ENDPOINT.format(device_id=self._device_id)
        async with self._session.post(
            url, data={"token": self._token}
        ) as resp:
            if resp.status in (401, 403):
                return None
            if resp.status != 200:
                raise AlkatronicApiError(f"Schedule test failed: HTTP {resp.status}")

            body = await resp.json()
            if not body.get("result"):
                raise AlkatronicApiError(
                    f"API returned failure: {body.get('message')}"
                )
            return True

    async def _fetch_records(self, days: int) -> list[dict[str, Any]] | None:
        url = RECORDS_ENDPOINT.format(device_id=self._device_id)
        params = {"token": self._token, "day": days}

        async with self._session.get(url, params=params) as resp:
            if resp.status in (401, 403):
                return None
            if resp.status != 200:
                raise AlkatronicApiError(f"Data fetch failed: HTTP {resp.status}")

            body = await resp.json()
            if not body.get("result"):
                raise AlkatronicApiError(
                    f"API returned failure: {body.get('message')}"
                )
            return body.get("data", [])
