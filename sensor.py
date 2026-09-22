"""PKU/loop sensors for Techlan Sensor (read-only)."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._shared.shared_entities import build_device_info
from .const import (
    CONF_HUMIDITY_LOOPS,
    CONF_HUMIDITY_OFFSET,
    CONF_HUMIDITY_SCALE,
    CONF_TEMPERATURE_LOOPS,
    CONF_TEMPERATURE_OFFSET,
    CONF_TEMPERATURE_SCALE,
    DEFAULT_HUMIDITY_OFFSET,
    DEFAULT_HUMIDITY_SCALE,
    DEFAULT_TEMPERATURE_OFFSET,
    DEFAULT_TEMPERATURE_SCALE,
    DOMAIN,
    RELAY_STATE_NAMES,
)
from .coordinator import TechlanDataUpdateCoordinator
from .relay_base import TechlanRelayEntity, configured_relays


def _pku_device_info(coordinator: TechlanDataUpdateCoordinator, pku: int) -> dict:
    """Child PKU device info with version-aware parent link (via_device_id / via_device)."""
    return build_device_info(
        identifiers={(DOMAIN, f"pku_{pku}")},
        name=f"Скиф ПКУ {pku}",
        model="ServerSkif PKU",
        configuration_url=coordinator.configuration_url,
        via_device_id=coordinator.parent_device_id,
        via_device=coordinator.parent_identifier,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    await coordinator.async_config_entry_first_refresh()
    config = {**entry.data, **entry.options}
    temperature_loops = set(config.get(CONF_TEMPERATURE_LOOPS, []) or [])
    humidity_loops = set(config.get(CONF_HUMIDITY_LOOPS, []) or [])
    entities = []
    for pku, item in coordinator.data.get("pkus", {}).items():
        for part, details in item.get("parts", {}).items():
            for sh, loop_details in details.get("loops", {}).items():
                entities.append(
                    TechlanLoopAdcSensor(
                        coordinator, entry, int(pku), int(part), int(sh), loop_details
                    )
                )
                if f"{pku}:{part}:{sh}" in temperature_loops:
                    entities.append(
                        TechlanTemperatureSensor(
                            coordinator,
                            entry,
                            int(pku),
                            int(part),
                            int(sh),
                            loop_details,
                        )
                    )
                if f"{pku}:{part}:{sh}" in humidity_loops:
                    entities.append(
                        TechlanHumiditySensor(
                            coordinator,
                            entry,
                            int(pku),
                            int(part),
                            int(sh),
                            loop_details,
                        )
                    )
    async_add_entities(entities)

    relay_entities: list = []
    for pku, relay in configured_relays(config):
        relay_entities.append(TechlanRelayStateSensor(coordinator, entry, pku, relay))
    async_add_entities(relay_entities)


class TechlanLoopAdcSensor(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity
):
    """Raw ADC reading for one selected ServerSkif loop."""

    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        part: int,
        sh: int,
        details: dict,
    ) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._description = str(details.get("description") or "").strip()
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_adc"
        self._attr_name = f"{self._description or f'ШС {sh >> 8}/{sh & 0xFF}'} АЦП"
        self._attr_device_info = _pku_device_info(coordinator, pku)

    def _details(self) -> dict:
        return (
            self.coordinator.data.get("pkus", {})
            .get(self._pku, {})
            .get("parts", {})
            .get(self._part, {})
            .get("loops", {})
            .get(self._sh, {})
        )

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
        return {
            "pku": self._pku,
            "part": self._part,
            "sh": self._sh,
            "sh_number": f"{self._sh >> 8}/{self._sh & 0xFF}",
            "description": self._description,
            "adc_raw": details.get("adc"),
            "adc_value": details.get("adc_value"),
        }


class TechlanTemperatureSensor(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity
):
    """Temperature entity calculated from the selected loop ADC value."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        part: int,
        sh: int,
        details: dict,
    ) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._description = str(details.get("description") or "").strip()
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_temperature"
        self._attr_name = (
            f"{self._description or f'ШС {sh >> 8}/{sh & 0xFF}'} температура"
        )
        self._attr_device_info = _pku_device_info(coordinator, pku)

    def _details(self) -> dict:
        return (
            self.coordinator.data.get("pkus", {})
            .get(self._pku, {})
            .get("parts", {})
            .get(self._part, {})
            .get("loops", {})
            .get(self._sh, {})
        )

    def _live_scale(self) -> float:
        return float(
            self.coordinator.option(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE)
        )

    def _live_offset(self) -> float:
        return float(
            self.coordinator.option(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET)
        )

    @property
    def native_value(self):
        details = self._details()
        value = details.get("temperature")
        if value is None:
            value = details.get("adc")
        try:
            return (
                round(float(value) * self._live_scale() + self._live_offset(), 2)
                if value is not None
                else None
            )
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
            "scale": self._live_scale(),
            "offset": self._live_offset(),
        }


class TechlanHumiditySensor(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity
):
    """Humidity entity calculated from the selected loop ADC value."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-percent"
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        part: int,
        sh: int,
        details: dict,
    ) -> None:
        super().__init__(coordinator)
        self._pku, self._part, self._sh = pku, part, sh
        self._description = str(details.get("description") or "").strip()
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_sh_{sh}_humidity"
        self._attr_name = (
            f"{self._description or f'ШС {sh >> 8}/{sh & 0xFF}'} влажность"
        )
        self._attr_device_info = _pku_device_info(coordinator, pku)

    def _details(self) -> dict:
        return (
            self.coordinator.data.get("pkus", {})
            .get(self._pku, {})
            .get("parts", {})
            .get(self._part, {})
            .get("loops", {})
            .get(self._sh, {})
        )

    def _live_scale(self) -> float:
        return float(
            self.coordinator.option(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE)
        )

    def _live_offset(self) -> float:
        return float(
            self.coordinator.option(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET)
        )

    @property
    def native_value(self):
        details = self._details()
        value = details.get("humidity")
        if value is None:
            value = details.get("adc")
        try:
            return (
                round(float(value) * self._live_scale() + self._live_offset(), 2)
                if value is not None
                else None
            )
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
            "scale": self._live_scale(),
            "offset": self._live_offset(),
        }


class TechlanRelayStateSensor(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SensorEntity, TechlanRelayEntity
):
    """Состояние реле ServerSkif (Включено / Выключено / Мигает)."""

    _relay_entity_suffix = "relay_state"
    _attr_has_entity_name = False
    _attr_icon = "mdi:electric-switch-closed"

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        relay: int,
    ) -> None:
        super().__init__(coordinator)
        self._init_relay(coordinator, entry, pku, relay)
        self._attr_name = f"{self._relay_name()} · состояние"

    @property
    def native_value(self) -> str:
        state = self._facts.get("state")
        if state is None:
            return "неизвестно"
        return RELAY_STATE_NAMES.get(state, f"код {state}")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._relay_extra(),
            "description": self._facts.get("description") or "",
        }
