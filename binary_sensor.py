"""Availability entity for Techlan ARM-OPS."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_STATE_CODES, CONF_TEMPERATURE_LOOPS, DOMAIN
from .coordinator import TechlanDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    entities = [TechlanAvailabilitySensor(coordinator)]
    temperature_loops = set({**entry.data, **entry.options}.get(CONF_TEMPERATURE_LOOPS, []) or [])
    for key in temperature_loops:
        try:
            pku, part, sh = (int(value) for value in key.split(":"))
        except (TypeError, ValueError):
            continue
        details = coordinator.data.get("pkus", {}).get(pku, {}).get("parts", {}).get(part, {}).get("loops", {}).get(sh, {})
        entities.append(TechlanTemperatureAlarmSensor(coordinator, pku, part, sh, str(details.get("description") or "").strip()))
    async_add_entities(entities)


class TechlanAvailabilitySensor(CoordinatorEntity[TechlanDataUpdateCoordinator], BinarySensorEntity):
    _attr_name = "Techlan Sensor доступность"
    _attr_unique_id = f"{DOMAIN}_availability"
    _attr_device_class = "connectivity"
    _attr_device_info = {
        "identifiers": {(DOMAIN, "arm_ops")},
        "name": "Techlan Sensor",
        "manufacturer": "Techlan",
        "model": "ServerSkif WebSocket proxy",
    }

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class TechlanTemperatureAlarmSensor(CoordinatorEntity[TechlanDataUpdateCoordinator], BinarySensorEntity):
    """Alarm state for a configured temperature loop."""

    _attr_device_class = "problem"
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator, pku: int, part: int, sh: int, description: str) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_temperature_alarm"
        self._attr_name = f"{description or f'ШС {sh >> 8}/{sh & 0xFF}'} температурная тревога"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"pku_{pku}")},
            "name": f"Скиф ПКУ {pku}",
            "manufacturer": "Techlan",
            "model": "ServerSkif PKU",
            "via_device": (DOMAIN, "sensor"),
        }

    def _details(self) -> dict:
        return self.coordinator.data.get("pkus", {}).get(self._pku, {}).get("parts", {}).get(self._part, {}).get("loops", {}).get(self._sh, {})

    @property
    def is_on(self) -> bool:
        try:
            code = int(self._details().get("state_code", -1))
        except (TypeError, ValueError):
            return False
        return code in ALARM_STATE_CODES or code in {206}
