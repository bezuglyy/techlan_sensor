"""Switch-сущности Techlan Sensor: реле и считыватели.

Реле — управляемый выход ServerSkif. ``switch`` использует программы ``on``/``off``
(``controlRelay`` с ``prog`` = 1/2). Текущее состояние берётся из опроса
(``getRelayState``): 1 — включено, 2 — выключено, 3 — мигает.

Считыватели (контроллеры доступа, напр. С2000-2) управляются ``controlReader``:
свободный проход (``free``/``normal``) и запрет доступа (``lock``/``normal``).

Реле — управляемый выход ServerSkif. ``switch`` использует программы ``on``/``off``
(``controlRelay`` с ``prog`` = 1/2). Текущее состояние берётся из опроса
(``getRelayState``): 1 — включено, 2 — выключено, 3 — мигает.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._shared.shared_api import reader_state_flags
from .const import RELAY_STATE_NAMES, RELAY_STATE_ON
from .coordinator import TechlanDataUpdateCoordinator
from .reader_base import TechlanReaderEntity, configured_readers
from .relay_base import TechlanRelayEntity, configured_relays


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up relay switches for the configured relays."""
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    config = {**entry.data, **entry.options}
    async_add_entities(
        TechlanRelaySwitch(coordinator, entry, pku, relay)
        for pku, relay in configured_relays(config)
    )
    reader_switches: list = []
    for pku, reader in configured_readers(config):
        reader_switches.append(TechlanReaderFreeSwitch(coordinator, entry, pku, reader))
        reader_switches.append(TechlanReaderLockSwitch(coordinator, entry, pku, reader))
    async_add_entities(reader_switches)


class TechlanRelaySwitch(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SwitchEntity, TechlanRelayEntity
):
    """On/off control for one ServerSkif relay."""

    _relay_entity_suffix = "relay_switch"
    _attr_has_entity_name = False
    _attr_icon = "mdi:electric-switch"

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        relay: int,
    ) -> None:
        super().__init__(coordinator)
        self._init_relay(coordinator, entry, pku, relay)
        self._attr_name = f"{self._relay_name()} · реле"

    @property
    def available(self) -> bool:
        return super().available and self._facts.get("state") is not None

    @property
    def is_on(self) -> bool:
        return self._facts.get("state") == RELAY_STATE_ON

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._facts.get("state")
        return {
            **self._relay_extra(),
            "state": RELAY_STATE_NAMES.get(state, "Неизвестно"),
            "description": self._facts.get("description") or "",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._apply_program("on")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._apply_program("off")
        await self.coordinator.async_request_refresh()


class TechlanReaderFreeSwitch(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SwitchEntity, TechlanReaderEntity
):
    """«Доступ открыт» — свободный проход (``controlReader`` free / normal)."""

    _reader_entity_suffix = "reader_free"
    _attr_has_entity_name = False
    _attr_icon = "mdi:door-open"

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        reader: int,
    ) -> None:
        super().__init__(coordinator)
        self._init_reader(coordinator, entry, pku, reader)
        self._attr_name = f"{self._reader_name()} · доступ открыт"

    @property
    def available(self) -> bool:
        return super().available and self._facts.get("state") is not None

    @property
    def is_on(self) -> bool:
        return reader_state_flags(self._facts.get("state"))["free"]

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._reader_extra(),
            **reader_state_flags(self._facts.get("state")),
            "description": self._facts.get("description") or "",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Открыть свободный доступ для всех (режим «Доступ открыт»)."""
        await self._apply_program("free")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Вернуть обычный режим доступа."""
        await self._apply_program("normal")
        await self.coordinator.async_request_refresh()


class TechlanReaderLockSwitch(
    CoordinatorEntity[TechlanDataUpdateCoordinator], SwitchEntity, TechlanReaderEntity
):
    """«Доступ запрещён» — запрет доступа (``controlReader`` lock / normal)."""

    _reader_entity_suffix = "reader_lock"
    _attr_has_entity_name = False
    _attr_icon = "mdi:door-closed-lock"

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        reader: int,
    ) -> None:
        super().__init__(coordinator)
        self._init_reader(coordinator, entry, pku, reader)
        self._attr_name = f"{self._reader_name()} · доступ запрещён"

    @property
    def available(self) -> bool:
        return super().available and self._facts.get("state") is not None

    @property
    def is_on(self) -> bool:
        flags = reader_state_flags(self._facts.get("state"))
        return bool(flags["entry_locked"] or flags["exit_locked"])

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._reader_extra(),
            **reader_state_flags(self._facts.get("state")),
            "description": self._facts.get("description") or "",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Запретить доступ по этому считывателю."""
        await self._apply_program("lock")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Снять запрет доступа (обычный режим)."""
        await self._apply_program("normal")
        await self.coordinator.async_request_refresh()


__all__ = [
    "TechlanReaderFreeSwitch",
    "TechlanReaderLockSwitch",
    "TechlanRelaySwitch",
]
