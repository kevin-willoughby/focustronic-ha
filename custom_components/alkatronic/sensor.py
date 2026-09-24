"""Sensor platform for Alkatronic.

Three groups of entities, all built from small description lists so adding
a new value later is just: add another description to the relevant list.

  - AlkatronicSensor        -> from the records coordinator (KH, pH, ...)
  - AlkatronicStatusSensor  -> from the device-status coordinator
                                (thresholds, last online, ...)
  - AlkatronicPumpSensor    -> one per Dosetronic pump, from the same
                                device-status coordinator (remaining volume)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_DOSETRONIC_ID, DOMAIN, SCALED_FIELDS
from .coordinator import AlkatronicCoordinator, AlkatronicDeviceStatusCoordinator

# ---------------------------------------------------------------------------
# Records-based sensors (KH, pH, dosing from the last test)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AlkatronicSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] | None = None


def _record_field(key: str) -> Callable[[dict[str, Any]], Any]:
    def _get(record: dict[str, Any]) -> Any:
        value = record.get(key)
        if value is None:
            return None
        if key in SCALED_FIELDS:
            return round(float(value) / 100, 2)
        return value

    return _get


RECORD_SENSOR_DESCRIPTIONS: tuple[AlkatronicSensorDescription, ...] = (
    AlkatronicSensorDescription(
        key="kh_value",
        name="KH",
        native_unit_of_measurement="dKH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_record_field("kh_value"),
    ),
    AlkatronicSensorDescription(
        key="ph_value",
        name="pH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_record_field("ph_value"),
    ),
    AlkatronicSensorDescription(
        key="acid_used",
        name="Acid Used",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_record_field("acid_used"),
    ),
    AlkatronicSensorDescription(
        key="solution_added",
        name="Solution Added",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_record_field("solution_added"),
    ),
    AlkatronicSensorDescription(
        key="record_time",
        name="Last Record Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda record: (
            datetime.fromtimestamp(record["record_time"], tz=timezone.utc)
            if record.get("record_time") is not None
            else None
        ),
    ),
)


class AlkatronicSensor(CoordinatorEntity[AlkatronicCoordinator], SensorEntity):
    """One value from the latest test record."""

    entity_description: AlkatronicSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AlkatronicCoordinator,
        description: AlkatronicSensorDescription,
        device_id: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Focustronic",
            model="Alkatronic",
        )

    @property
    def native_value(self) -> Any:
        latest = self.coordinator.latest
        if latest is None or self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(latest)


class AlkatronicHistorySensor(CoordinatorEntity[AlkatronicCoordinator], SensorEntity):
    """Expose the full retrieved test history as sensor attributes."""

    _attr_has_entity_name = True
    _attr_name = "Test History"
    _attr_native_unit_of_measurement = "records"
    # The full record list can exceed the recorder's 16 KB attribute limit
    # (168 hourly records over 7 days is already ~17 KB as JSON); keep it
    # out of the state history and available only as a live attribute.
    _unrecorded_attributes = frozenset({"records"})

    def __init__(
        self, coordinator: AlkatronicCoordinator, device_id: str, device_name: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_id}_test_history"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Focustronic",
            model="Alkatronic",
        )

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = []
        for record in self.coordinator.data or []:
            record_time = record.get("record_time")
            records.append(
                {
                    "record_time": (
                        datetime.fromtimestamp(record_time, tz=timezone.utc).isoformat()
                        if record_time is not None
                        else None
                    ),
                    "kh": _record_field("kh_value")(record),
                    "ph": _record_field("ph_value")(record),
                    "acid_used": record.get("acid_used"),
                    "solution_added": record.get("solution_added"),
                }
            )
        return {"records": records}


# ---------------------------------------------------------------------------
# Device-status sensors (thresholds, last online — from /users/self/devices)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AlkatronicStatusSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] | None = None


def _timestamp_field(key: str) -> Callable[[dict[str, Any]], Any]:
    def _get(dev: dict[str, Any]) -> Any:
        value = dev.get(key)
        return datetime.fromtimestamp(value, tz=timezone.utc) if value else None

    return _get


STATUS_SENSOR_DESCRIPTIONS: tuple[AlkatronicStatusSensorDescription, ...] = (
    AlkatronicStatusSensorDescription(
        key="upper_kh",
        name="Upper KH Threshold",
        native_unit_of_measurement="dKH",
        value_fn=lambda dev: round(dev["settings"]["upper_kh"] / 100, 2),
    ),
    AlkatronicStatusSensorDescription(
        key="lower_kh",
        name="Lower KH Threshold",
        native_unit_of_measurement="dKH",
        value_fn=lambda dev: round(dev["settings"]["lower_kh"] / 100, 2),
    ),
    AlkatronicStatusSensorDescription(
        key="last_online",
        name="Last Online",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_timestamp_field("last_online"),
    ),
    AlkatronicStatusSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev.get("firmware_version"),
    ),
    AlkatronicStatusSensorDescription(
        key="local_ip_address",
        name="IP Address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev.get("local_ip_address"),
    ),
    AlkatronicStatusSensorDescription(
        key="lifetime_test_count",
        name="Lifetime Test Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev.get("lifetime_test_count"),
    ),
    AlkatronicStatusSensorDescription(
        key="current_test_count",
        name="Current Test Count",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev["settings"].get("current_test_count"),
    ),
    AlkatronicStatusSensorDescription(
        key="test_count_limit",
        name="Test Count Limit",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev["settings"].get("test_count_limit"),
    ),
    AlkatronicStatusSensorDescription(
        key="measure_interval",
        name="Measure Interval",
        native_unit_of_measurement="h",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev["settings"].get("measure_interval"),
    ),
    AlkatronicStatusSensorDescription(
        key="aquarium_volume",
        name="Aquarium Volume",
        native_unit_of_measurement="L",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev["settings"].get("aquarium_volume"),
    ),
    AlkatronicStatusSensorDescription(
        key="last_error_code",
        name="Last Error Code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev.get("last_error_code") or None,
    ),
    AlkatronicStatusSensorDescription(
        key="last_error_time",
        name="Last Error Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_timestamp_field("last_error_time"),
    ),
)


DOSETRONIC_STATUS_SENSOR_DESCRIPTIONS: tuple[AlkatronicStatusSensorDescription, ...] = (
    AlkatronicStatusSensorDescription(
        key="last_online",
        name="Last Online",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_timestamp_field("last_online"),
    ),
    AlkatronicStatusSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev.get("firmware_version"),
    ),
    AlkatronicStatusSensorDescription(
        key="local_ip_address",
        name="IP Address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda dev: dev.get("local_ip_address"),
    ),
)


class AlkatronicStatusSensor(
    CoordinatorEntity[AlkatronicDeviceStatusCoordinator], SensorEntity
):
    """One value from the account-wide device-status endpoint, for one device."""

    entity_description: AlkatronicStatusSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AlkatronicDeviceStatusCoordinator,
        description: AlkatronicStatusSensorDescription,
        device_id: str,
        device_name: str,
        device_type: str = "alkatronic",
        model: str = "Alkatronic",
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._device_type = device_type
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Focustronic",
            model=model,
        )

    def _find_device(self) -> dict[str, Any] | None:
        devices = (self.coordinator.data or {}).get(self._device_type, [])
        return next((d for d in devices if str(d["id"]) == self._device_id), None)

    @property
    def native_value(self) -> Any:
        device = self._find_device()
        if device is None or self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(device)


# ---------------------------------------------------------------------------
# Dosetronic pump sensors — remaining solution per pump
# ---------------------------------------------------------------------------


class AlkatronicPumpSensor(
    CoordinatorEntity[AlkatronicDeviceStatusCoordinator], SensorEntity
):
    """Remaining volume for one Dosetronic pump."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "mL"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: AlkatronicDeviceStatusCoordinator,
        dosetronic_id: str,
        pump_id: int,
        pump_name: str,
        device_name: str = "Dosetronic",
    ) -> None:
        super().__init__(coordinator)
        self._dosetronic_id = dosetronic_id
        self._pump_id = pump_id
        self._attr_name = f"{pump_name} Remaining"
        self._attr_unique_id = f"{dosetronic_id}_pump_{pump_id}_remaining"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dosetronic_id)},
            name=device_name,
            manufacturer="Focustronic",
            model="Dosetronic",
        )

    def _find_pump(self) -> dict[str, Any] | None:
        devices = (self.coordinator.data or {}).get("dosetronic", [])
        device = next(
            (d for d in devices if str(d["id"]) == self._dosetronic_id), None
        )
        if device is None:
            return None
        return next(
            (p for p in device["settings"]["pumps"] if p["id"] == self._pump_id),
            None,
        )

    @property
    def native_value(self) -> Any:
        pump = self._find_pump()
        if pump is None:
            return None
        # remaining_volume is in µL in the API; convert to mL. Can go
        # negative if the pump's counter hasn't been reset after a refill —
        # clamp at 0 rather than showing a confusing negative number.
        return max(round(pump["remaining_volume"] / 1000, 1), 0)


class AlkatronicPumpMaxVolumeSensor(
    CoordinatorEntity[AlkatronicDeviceStatusCoordinator], SensorEntity
):
    """Volume the pump's reservoir was set to at its last refill/reset.

    The API calls this field "max_volume", but it isn't a fixed hardware
    limit — it's whatever volume was entered when the bottle was last
    refilled, and it's the denominator used to compute remaining-percent.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "mL"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: AlkatronicDeviceStatusCoordinator,
        dosetronic_id: str,
        pump_id: int,
        pump_name: str,
        device_name: str = "Dosetronic",
    ) -> None:
        super().__init__(coordinator)
        self._dosetronic_id = dosetronic_id
        self._pump_id = pump_id
        self._attr_name = f"{pump_name} Refill Volume"
        self._attr_unique_id = f"{dosetronic_id}_pump_{pump_id}_max_volume"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dosetronic_id)},
            name=device_name,
            manufacturer="Focustronic",
            model="Dosetronic",
        )

    def _find_pump(self) -> dict[str, Any] | None:
        devices = (self.coordinator.data or {}).get("dosetronic", [])
        device = next(
            (d for d in devices if str(d["id"]) == self._dosetronic_id), None
        )
        if device is None:
            return None
        return next(
            (p for p in device["settings"]["pumps"] if p["id"] == self._pump_id),
            None,
        )

    @property
    def native_value(self) -> Any:
        pump = self._find_pump()
        return round(pump["max_volume"] / 1000, 1) if pump else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "note": (
                "Volume set when the pump reservoir was last refilled/reset, "
                "not a fixed hardware capacity."
            )
        }


class AlkatronicPumpRemainingPercentSensor(
    CoordinatorEntity[AlkatronicDeviceStatusCoordinator], SensorEntity
):
    """Remaining volume for one Dosetronic pump, as a percentage of its max."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: AlkatronicDeviceStatusCoordinator,
        dosetronic_id: str,
        pump_id: int,
        pump_name: str,
        device_name: str = "Dosetronic",
    ) -> None:
        super().__init__(coordinator)
        self._dosetronic_id = dosetronic_id
        self._pump_id = pump_id
        self._attr_name = f"{pump_name} Remaining %"
        self._attr_unique_id = f"{dosetronic_id}_pump_{pump_id}_remaining_percent"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dosetronic_id)},
            name=device_name,
            manufacturer="Focustronic",
            model="Dosetronic",
        )

    def _find_pump(self) -> dict[str, Any] | None:
        devices = (self.coordinator.data or {}).get("dosetronic", [])
        device = next(
            (d for d in devices if str(d["id"]) == self._dosetronic_id), None
        )
        if device is None:
            return None
        return next(
            (p for p in device["settings"]["pumps"] if p["id"] == self._pump_id),
            None,
        )

    @property
    def native_value(self) -> Any:
        pump = self._find_pump()
        if pump is None or not pump.get("max_volume"):
            return None
        percent = 100 * pump["remaining_volume"] / pump["max_volume"]
        return max(round(percent, 1), 0)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    records_coordinator: AlkatronicCoordinator = coordinators["records"]
    status_coordinator: AlkatronicDeviceStatusCoordinator = coordinators["status"]

    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Alkatronic")

    entities: list[SensorEntity] = [
        AlkatronicSensor(records_coordinator, description, device_id, device_name)
        for description in RECORD_SENSOR_DESCRIPTIONS
    ] + [
        AlkatronicHistorySensor(records_coordinator, device_id, device_name),
    ] + [
        AlkatronicStatusSensor(status_coordinator, description, device_id, device_name)
        for description in STATUS_SENSOR_DESCRIPTIONS
    ]

    dosetronic_id = entry.data.get(CONF_DOSETRONIC_ID)
    if dosetronic_id:
        status_devices = (status_coordinator.data or {}).get("dosetronic", [])
        dosetronic_device = next(
            (d for d in status_devices if str(d["id"]) == dosetronic_id), None
        )
        if dosetronic_device:
            dosetronic_name = (
                dosetronic_device.get("friendly_name")
                or dosetronic_device["serial_number"]
            )
            entities += [
                AlkatronicStatusSensor(
                    status_coordinator,
                    description,
                    dosetronic_id,
                    dosetronic_name,
                    device_type="dosetronic",
                    model="Dosetronic",
                )
                for description in DOSETRONIC_STATUS_SENSOR_DESCRIPTIONS
            ]
            for pump in dosetronic_device["settings"]["pumps"]:
                entities.append(
                    AlkatronicPumpSensor(
                        status_coordinator,
                        dosetronic_id,
                        pump["id"],
                        pump["name"],
                        dosetronic_name,
                    )
                )
                entities.append(
                    AlkatronicPumpMaxVolumeSensor(
                        status_coordinator,
                        dosetronic_id,
                        pump["id"],
                        pump["name"],
                        dosetronic_name,
                    )
                )
                entities.append(
                    AlkatronicPumpRemainingPercentSensor(
                        status_coordinator,
                        dosetronic_id,
                        pump["id"],
                        pump["name"],
                        dosetronic_name,
                    )
                )

    async_add_entities(entities)
