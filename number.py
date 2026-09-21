"""Number-сущности калибровки для Techlan Sensor.

Только чтение датчиков, но пользователю нужны уставки: коэффициенты
пересчёта АЦП (``scale``/``offset``) и пороги климатической тревоги. Значения
сохраняются в ``options`` config entry (через ``async_update_entry``) и
применяются к сенсорам без пересоздания интеграции.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._shared.shared_entities import build_device_info
from .const import (
    CONF_HUMIDITY_OFFSET,
    CONF_HUMIDITY_SCALE,
    CONF_TEMPERATURE_ALARM_HIGH,
    CONF_TEMPERATURE_ALARM_LOW,
    CONF_TEMPERATURE_OFFSET,
    CONF_TEMPERATURE_SCALE,
    DEFAULT_HUMIDITY_OFFSET,
    DEFAULT_HUMIDITY_SCALE,
    DEFAULT_TEMPERATURE_ALARM_HIGH,
    DEFAULT_TEMPERATURE_ALARM_LOW,
    DEFAULT_TEMPERATURE_OFFSET,
    DEFAULT_TEMPERATURE_SCALE,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
    INTEGRATION_VERSION,
)
from .coordinator import TechlanDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class TechlanNumber:
    """Static definition of one calibration number entity."""

    key: str
    name: str
    minimum: float
    maximum: float
    step: float
    default: float
    icon: str
    unit: str | None = None


CALIBRATION_NUMBERS: tuple[TechlanNumber, ...] = (
    TechlanNumber(
        key=CONF_TEMPERATURE_SCALE,
        name="Калибровка: температура × scale",
        minimum=0.01,
        maximum=100.0,
        step=0.01,
        default=DEFAULT_TEMPERATURE_SCALE,
        icon="mdi:scale",
    ),
    TechlanNumber(
        key=CONF_TEMPERATURE_OFFSET,
        name="Калибровка: температура + offset",
        minimum=-100.0,
        maximum=100.0,
        step=0.1,
        default=DEFAULT_TEMPERATURE_OFFSET,
        icon="mdi:plus-minus-variant",
        unit="°C",
    ),
    TechlanNumber(
        key=CONF_HUMIDITY_SCALE,
        name="Калибровка: влажность × scale",
        minimum=0.01,
        maximum=100.0,
        step=0.01,
        default=DEFAULT_HUMIDITY_SCALE,
        icon="mdi:scale",
    ),
    TechlanNumber(
        key=CONF_HUMIDITY_OFFSET,
        name="Калибровка: влажность + offset",
        minimum=-100.0,
        maximum=100.0,
        step=0.1,
        default=DEFAULT_HUMIDITY_OFFSET,
        icon="mdi:plus-minus-variant",
        unit="%",
    ),
    TechlanNumber(
        key=CONF_TEMPERATURE_ALARM_LOW,
        name="Порог тревоги: температура ниже",
        minimum=-50.0,
        maximum=150.0,
        step=0.1,
        default=DEFAULT_TEMPERATURE_ALARM_LOW,
        icon="mdi:thermometer-low",
        unit="°C",
    ),
    TechlanNumber(
        key=CONF_TEMPERATURE_ALARM_HIGH,
        name="Порог тревоги: температура выше",
        minimum=-50.0,
        maximum=150.0,
        step=0.1,
        default=DEFAULT_TEMPERATURE_ALARM_HIGH,
        icon="mdi:thermometer-high",
        unit="°C",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Techlan Sensor calibration numbers."""
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        TechlanCalibrationNumber(coordinator, entry, definition)
        for definition in CALIBRATION_NUMBERS
    )


class TechlanCalibrationNumber(
    CoordinatorEntity[TechlanDataUpdateCoordinator], NumberEntity
):
    """A persistent calibration/threshold number stored in entry options."""

    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        definition: TechlanNumber,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._definition = definition
        self._attr_unique_id = f"{DOMAIN}_{definition.key}"
        self._attr_name = definition.name
        self._attr_native_min_value = definition.minimum
        self._attr_native_max_value = definition.maximum
        self._attr_native_step = definition.step
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_icon = definition.icon
        self._attr_suggested_display_precision = 2
        self._attr_device_info = build_device_info(
            identifiers={coordinator.parent_identifier},
            name=DEVICE_NAME,
            model=DEVICE_MODEL,
            sw_version=INTEGRATION_VERSION,
            configuration_url=coordinator.configuration_url,
        )

    @property
    def native_value(self) -> float:
        return float(
            self.coordinator.option(self._definition.key, self._definition.default)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new value into options and apply it live."""
        options: dict[str, Any] = {
            **self._entry.options,
            self._definition.key: float(value),
        }
        self.hass.config_entries.async_update_entry(self._entry, options=options)
        self.coordinator.update_runtime_options({**self._entry.data, **options})
        self.async_write_ha_state()
