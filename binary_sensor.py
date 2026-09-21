"""Availability and climate-alarm entities for Techlan Sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._shared.shared_entities import build_device_info
from .const import (
    ALARM_STATE_CODES,
    CONF_TEMPERATURE_ALARM_HIGH,
    CONF_TEMPERATURE_ALARM_LOW,
    CONF_TEMPERATURE_LOOPS,
    CONF_TEMPERATURE_OFFSET,
    CONF_TEMPERATURE_SCALE,
    DEFAULT_TEMPERATURE_ALARM_HIGH,
    DEFAULT_TEMPERATURE_ALARM_LOW,
    DEFAULT_TEMPERATURE_OFFSET,
    DEFAULT_TEMPERATURE_SCALE,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
    INTEGRATION_VERSION,
    TEMPERATURE_ALARM_CODE,
)
from .coordinator import TechlanDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    entities = [TechlanAvailabilitySensor(coordinator)]
    temperature_loops = set(
        {**entry.data, **entry.options}.get(CONF_TEMPERATURE_LOOPS, []) or []
    )
    for key in temperature_loops:
        try:
            pku, part, sh = (int(value) for value in key.split(":"))
        except (TypeError, ValueError):
            continue
        details = (
            coordinator.data.get("pkus", {})
            .get(pku, {})
            .get("parts", {})
            .get(part, {})
            .get("loops", {})
            .get(sh, {})
        )
        entities.append(
            TechlanTemperatureAlarmSensor(
                coordinator,
                pku,
                part,
                sh,
                str(details.get("description") or "").strip(),
            )
        )
    async_add_entities(entities)


class TechlanAvailabilitySensor(
    CoordinatorEntity[TechlanDataUpdateCoordinator], BinarySensorEntity
):
    """Service entity: ARM-OPS reachability (diagnostic)."""

    _attr_has_entity_name = True
    _attr_translation_key = "availability"
    _attr_unique_id = f"{DOMAIN}_availability"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TechlanDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = build_device_info(
            identifiers={coordinator.parent_identifier},
            name=DEVICE_NAME,
            model=DEVICE_MODEL,
            sw_version=INTEGRATION_VERSION,
            configuration_url=coordinator.configuration_url,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class TechlanTemperatureAlarmSensor(
    CoordinatorEntity[TechlanDataUpdateCoordinator], BinarySensorEntity
):
    """Alarm state for a configured temperature loop."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:thermometer-alert"
    _attr_has_entity_name = False

    def __init__(
        self, coordinator, pku: int, part: int, sh: int, description: str
    ) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._attr_unique_id = (
            f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_temperature_alarm"
        )
        self._attr_name = (
            f"{description or f'ШС {sh >> 8}/{sh & 0xFF}'} температурная тревога"
        )
        self._attr_device_info = build_device_info(
            identifiers={(DOMAIN, f"pku_{pku}")},
            name=f"Скиф ПКУ {pku}",
            model="ServerSkif PKU",
            configuration_url=coordinator.configuration_url,
            via_device_id=coordinator.parent_device_id,
            via_device=coordinator.parent_identifier,
        )

    def _details(self) -> dict:
        return (
            self.coordinator.data.get("pkus", {})
            .get(self._pku, {})
            .get("parts", {})
            .get(self._part, {})
            .get("loops", {})
            .get(self._sh, {})
        )

    def _computed_temperature(self) -> float | None:
        details = self._details()
        value = details.get("temperature")
        if value is None:
            value = details.get("adc")
        if value is None:
            return None
        scale = float(
            self.coordinator.option(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE)
        )
        offset = float(
            self.coordinator.option(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET)
        )
        try:
            return float(value) * scale + offset
        except (TypeError, ValueError):
            return None

    @property
    def is_on(self) -> bool:
        try:
            code = int(self._details().get("state_code", -1))
        except (TypeError, ValueError):
            code = -1
        if code in ALARM_STATE_CODES or code == TEMPERATURE_ALARM_CODE:
            return True
        temperature = self._computed_temperature()
        if temperature is None:
            return False
        low = float(
            self.coordinator.option(
                CONF_TEMPERATURE_ALARM_LOW, DEFAULT_TEMPERATURE_ALARM_LOW
            )
        )
        high = float(
            self.coordinator.option(
                CONF_TEMPERATURE_ALARM_HIGH, DEFAULT_TEMPERATURE_ALARM_HIGH
            )
        )
        return temperature < low or temperature > high

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "pku": self._pku,
            "part": self._part,
            "sh": self._sh,
            "temperature": self._computed_temperature(),
            "alarm_low": self.coordinator.option(
                CONF_TEMPERATURE_ALARM_LOW, DEFAULT_TEMPERATURE_ALARM_LOW
            ),
            "alarm_high": self.coordinator.option(
                CONF_TEMPERATURE_ALARM_HIGH, DEFAULT_TEMPERATURE_ALARM_HIGH
            ),
        }
