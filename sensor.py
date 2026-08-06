"""PKU summary sensors for Techlan ARM-OPS."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_STATE_CODES, CONF_HUMIDITY_LOOPS, CONF_HUMIDITY_OFFSET, CONF_HUMIDITY_SCALE, CONF_TEMPERATURE_LOOPS, CONF_TEMPERATURE_OFFSET, CONF_TEMPERATURE_SCALE, DEFAULT_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_SCALE, DEFAULT_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_SCALE, DOMAIN, STATE_NAMES
from .coordinator import TechlanDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    await coordinator.async_config_entry_first_refresh()
    config = {**entry.data, **entry.options}
    temperature_loops = set(config.get(CONF_TEMPERATURE_LOOPS, []) or [])
    temperature_scale = float(config.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE))
    temperature_offset = float(config.get(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET))
    humidity_loops = set(config.get(CONF_HUMIDITY_LOOPS, []) or [])
    humidity_scale = float(config.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE))
    humidity_offset = float(config.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET))
    entities = []
    for pku, item in coordinator.data.get("pkus", {}).items():
        for part, details in item.get("parts", {}).items():
            for sh, loop_details in details.get("loops", {}).items():
                entities.append(TechlanLoopAdcSensor(coordinator, entry, int(pku), int(part), int(sh), loop_details))
                if f"{pku}:{part}:{sh}" in temperature_loops:
                    entities.append(TechlanTemperatureSensor(coordinator, entry, int(pku), int(part), int(sh), loop_details, temperature_scale, temperature_offset))
                if f"{pku}:{part}:{sh}" in humidity_loops:
                    entities.append(TechlanHumiditySensor(coordinator, entry, int(pku), int(part), int(sh), loop_details, humidity_scale, humidity_offset))
    async_add_entities(entities)


class TechlanPkuSensor(CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity):
    """One compact sensor per PKU; details are exposed as attributes."""

    _attr_icon = "mdi:shield-home-outline"

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, entry: ConfigEntry, pku: int) -> None:
        super().__init__(coordinator)
        self._pku = pku
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}"
        self._attr_name = f"Скиф ПКУ {pku}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"pku_{pku}")},
            "name": f"Скиф ПКУ {pku}",
            "manufacturer": "Techlan",
            "model": "ServerSkif PKU",
            "via_device": (DOMAIN, "arm_ops"),
        }

    @property
    def native_value(self) -> str:
        return "online" if self.coordinator.last_update_success else "offline"

    @property
    def extra_state_attributes(self) -> dict:
        item = self.coordinator.data.get("pkus", {}).get(self._pku, {})
        return {"pku": self._pku, "part_count": item.get("part_count", 0), "parts": item.get("parts", {})}


class TechlanPartSensor(CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity):
    """State entity for one ARM security/fire section."""

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, entry: ConfigEntry, pku: int, part: int, details: dict) -> None:
        super().__init__(coordinator)
        self._pku = pku
        self._part = part
        self._description = str(details.get("description") or "").strip()
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}"
        self._attr_name = self._name()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"pku_{pku}")},
            "name": f"Скиф ПКУ {pku}",
            "manufacturer": "Techlan",
            "model": "ServerSkif PKU",
            "via_device": (DOMAIN, "arm_ops"),
        }

    def _name(self) -> str:
        return self._description or "Без названия"

    def _details(self) -> dict:
        return self.coordinator.data.get("pkus", {}).get(self._pku, {}).get("parts", {}).get(self._part, {})

    @property
    def native_value(self) -> str:
        code = int(self._details().get("state_code", -1))
        return STATE_NAMES.get(code, "Тревога" if code in ALARM_STATE_CODES else f"Состояние {code}")

    @property
    def icon(self) -> str:
        details = self._details()
        code = int(details.get("state_code", -1))
        text = f"{self._description} {STATE_NAMES.get(code, '')}".lower()
        if code in ALARM_STATE_CODES:
            if any(word in text for word in ("пожар", "дым", "температур", "затоп")):
                return "mdi:shield-fire-outline"
            return "mdi:shield-alert-outline"
        if code in {109, 119} or "снят" in text:
            return "mdi:shield-off-outline"
        return "mdi:shield-check-outline"

    @property
    def extra_state_attributes(self) -> dict:
        details = self._details()
        return {
            "pku": self._pku,
            "part": self._part,
            "description": self._description,
            "state_code": details.get("state_code"),
        }


class TechlanLoopAdcSensor(CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity):
    """Raw ADC reading for one selected ServerSkif loop."""

    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_state_class = "measurement"

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, entry: ConfigEntry, pku: int, part: int, sh: int, details: dict) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._description = str(details.get("description") or "").strip()
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_adc"
        self._attr_name = f"{self._description or f'ШС {sh >> 8}/{sh & 0xFF}'} АЦП"
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
    def native_value(self):
        # ret is the numeric ADC value. adc_value is ServerSkif's formatted
        # human-readable resistance string (for example, "4.7 кОм").
        value = self._details().get("adc")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        details = self._details()
        return {"pku": self._pku, "part": self._part, "sh": self._sh, "sh_number": f"{self._sh >> 8}/{self._sh & 0xFF}", "description": self._description, "adc_raw": details.get("adc"), "adc_value": details.get("adc_value")}


class TechlanTemperatureSensor(CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity):
    """Temperature entity calculated from the selected loop ADC value."""

    _attr_device_class = "temperature"
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = "measurement"
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, entry: ConfigEntry, pku: int, part: int, sh: int, details: dict, scale: float, offset: float) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._description = str(details.get("description") or "").strip()
        self._scale, self._offset = scale, offset
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_temperature"
        self._attr_name = f"{self._description or f'ШС {sh >> 8}/{sh & 0xFF}'} температура"
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
    def native_value(self):
        details = self._details()
        value = details.get("temperature")
        if value is None:
            value = details.get("adc")
        try:
            return round(float(value) * self._scale + self._offset, 2) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        details = self._details()
        return {
            "pku": self._pku,
            "part": self._part,
            "sh": self._sh,
            "sh_number": f"{self._sh >> 8}/{self._sh & 0xFF}",
            "description": self._description,
            "adc_raw": details.get("adc"),
            "adc_value": details.get("adc_value"),
            "conversion": "temperature = adc × scale + offset",
            "scale": self._scale,
            "offset": self._offset,
        }


class TechlanHumiditySensor(CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity):
    """Humidity entity calculated from the selected loop ADC value."""

    _attr_device_class = "humidity"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = "measurement"
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, entry: ConfigEntry, pku: int, part: int, sh: int, details: dict, scale: float, offset: float) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._description = str(details.get("description") or "").strip()
        self._scale, self._offset = scale, offset
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_humidity"
        self._attr_name = f"{self._description or f'ШС {sh >> 8}/{sh & 0xFF}'} влажность"
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
    def native_value(self):
        details = self._details()
        value = details.get("humidity")
        if value is None:
            value = details.get("adc")
        try:
            return round(float(value) * self._scale + self._offset, 2) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        details = self._details()
        return {
            "pku": self._pku,
            "part": self._part,
            "sh": self._sh,
            "sh_number": f"{self._sh >> 8}/{self._sh & 0xFF}",
            "description": self._description,
            "adc_raw": details.get("adc"),
            "adc_value": details.get("adc_value"),
            "conversion": "humidity = adc × scale + offset",
            "scale": self._scale,
            "offset": self._offset,
        }
