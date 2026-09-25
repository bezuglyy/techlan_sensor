"""Button-сущности Techlan Sensor: реле и считыватели (контроллеры доступа).

Кнопка «Переключить» отправляет ``controlRelay_Inv`` — инверсию состояния реле
(то же, что делает клиент АРМ «Скиф» по клику на состоянии реле).
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TechlanDataUpdateCoordinator
from .reader_base import TechlanReaderEntity, configured_readers
from .relay_base import TechlanRelayEntity, configured_relays


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up relay toggle buttons for the configured relays."""
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    config = {**entry.data, **entry.options}
    async_add_entities(
        TechlanRelayToggleButton(coordinator, entry, pku, relay)
        for pku, relay in configured_relays(config)
    )
    async_add_entities(
        TechlanReaderOpenButton(coordinator, entry, pku, reader)
        for pku, reader in configured_readers(config)
    )


class TechlanRelayToggleButton(
    CoordinatorEntity[TechlanDataUpdateCoordinator], ButtonEntity, TechlanRelayEntity
):
    """Toggle one ServerSkif relay (``controlRelay_Inv``)."""

    _relay_entity_suffix = "relay_toggle"
    _attr_has_entity_name = False
    _attr_icon = "mdi:toggle-switch-variant"

    def __init__(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        relay: int,
    ) -> None:
        super().__init__(coordinator)
        self._init_relay(coordinator, entry, pku, relay)
        self._attr_name = f"{self._relay_name()} · переключить"

    async def async_press(self) -> None:
        await self.coordinator.client.async_invert_relay(self._pku, self._relay)
        await self.coordinator.async_request_refresh()


class TechlanReaderOpenButton(
    CoordinatorEntity[TechlanDataUpdateCoordinator], ButtonEntity, TechlanReaderEntity
):
    """«Открыть доступ» — разовое предоставление доступа (controlReader, prog 0).

    Для контроллеров доступа (С2000-2): реле прибора управляются только логикой
    доступа, поэтому открытие выполняется командой считывателю.
    """

    _reader_entity_suffix = "reader_open"
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
        self._attr_name = f"{self._reader_name()} · открыть доступ"

    async def async_press(self) -> None:
        await self._apply_program("open")
        await self.coordinator.async_request_refresh()


__all__ = ["TechlanReaderOpenButton", "TechlanRelayToggleButton"]
