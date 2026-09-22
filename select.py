"""Select-сущность: программа управления реле Techlan Sensor.

Полный набор программ вендора (``RL_*``):

==============  ====  ==================================================
option          prog  смысл
==============  ====  ==================================================
``reset``       0     Сброс
``on``          1     Включить
``off``         2     Выключить
``on_time``     3     Включить на время (см. number «время»)
``off_time``    4     Выключить на время
``blink_off``   5     Мигать из состояния ВЫКЛЮЧЕНО
``blink_on``    6     Мигать из состояния ВКЛЮЧЕНО
``blink_off_time`` 7  Мигать из ВЫКЛЮЧЕНО на время
``blink_on_time``  8  Мигать из ВКЛЮЧЕНО на время
==============  ====  ==================================================

Выбор значения применяет программу немедленно и запоминается в options
(``CONF_RELAY_PROGRAM``), чтобы после перезапуска отображать последнюю выбранную.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_RELAY_PROGRAM,
    DEFAULT_RELAY_PROGRAM,
    RELAY_PROGRAMS,
)
from .coordinator import TechlanDataUpdateCoordinator
from .relay_base import TechlanRelayEntity, configured_relays

# Порядок и подписи в UI (канон RL_* вендора).
PROGRAM_LABELS: dict[str, str] = {
    "reset": "Сброс",
    "on": "Включить",
    "off": "Выключить",
    "on_time": "Включить на время",
    "off_time": "Выключить на время",
    "blink_off": "Мигать из ВЫКЛЮЧЕНО",
    "blink_on": "Мигать из ВКЛЮЧЕНО",
    "blink_off_time": "Мигать из ВЫКЛЮЧЕНО (на время)",
    "blink_on_time": "Мигать из ВКЛЮЧЕНО (на время)",
}

_OPTION_BY_LABEL = {label: name for name, label in PROGRAM_LABELS.items()}
_LABEL_BY_OPTION = dict(PROGRAM_LABELS)
_ORDER = [
    "on",
    "off",
    "reset",
    "on_time",
    "off_time",
    "blink_off",
    "blink_on",
    "blink_off_time",
    "blink_on_time",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up relay program selects for the configured relays."""
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    config = {**entry.data, **entry.options}
    async_add_entities(
        TechlanRelayProgramSelect(coordinator, entry, pku, relay)
        for pku, relay in configured_relays(config)
    )


class TechlanRelayProgramSelect(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SelectEntity, TechlanRelayEntity
):
    """Program selector for one ServerSkif relay."""

    _relay_entity_suffix = "relay_program"
    _attr_has_entity_name = False
    _attr_icon = "mdi:playlist-play"
    _attr_options = [_LABEL_BY_OPTION[name] for name in _ORDER]

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        relay: int,
    ) -> None:
        super().__init__(coordinator)
        self._init_relay(coordinator, entry, pku, relay)
        self._attr_name = f"{self._relay_name()} · программа"

    @property
    def current_option(self) -> str:
        program = self.relay_program
        if program not in RELAY_PROGRAMS:
            program = DEFAULT_RELAY_PROGRAM
        return _LABEL_BY_OPTION.get(program, _LABEL_BY_OPTION[DEFAULT_RELAY_PROGRAM])

    async def async_select_option(self, option: str) -> None:
        program = _OPTION_BY_LABEL.get(option)
        if program is None:
            return
        await self._apply_program(program)
        await self._store_option_map(CONF_RELAY_PROGRAM, {self._relay_key: program})
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


__all__ = ["TechlanRelayProgramSelect", "PROGRAM_LABELS"]
