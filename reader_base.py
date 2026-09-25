"""Общая база для reader-сущностей Techlan Sensor (контроллеры доступа).

Считыватель ServerSkif — канал контроллера **доступа** (например С2000-2),
адресуемый парой ``(pku, rd)``, где ``rd = (device << 8) | reader_number``.

Почему считыватель, а не реле: у контроллеров доступа (С2000-2) реле — это
«замки», которыми управляет только логика доступа прибора (в РЭ С2000-2,
Таблица 12, у реле есть лишь программы 3/4 «включить/выключить на время»).
Внешнее управление реле прибор не поддерживает — поэтому команда
``controlRelay`` для С2000-2 не действует. Правильный путь — ``controlReader``
(Таблица А.4 приложения к протоколу АРМ «Скиф»): 0 — предоставление доступа,
1 — норма, 4 — запрет доступа, 7 — открытие свободного доступа.

Оператор выбирает считыватели в настройках (``CONF_SELECTED_READERS`` =
``["pku:rd", ...]``), после чего интеграция создаёт набор сущностей на каждом:

* ``sensor``  — состояние (доступ разрешён / запрет / свободный проход);
* ``button``  — «Открыть доступ» (программа ``open``);
* ``switch``  — «Доступ открыт» (свободный проход, программы ``free``/``normal``);
* ``switch``  — «Доступ запрещён» (программа ``lock``/``normal``).

Источник данных — ``coordinator.data["readers"]`` (см. ``api._read_readers_sync``).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from ._shared.shared_api import decode_reader, parse_reader_keys, reader_key
from ._shared.shared_entities import build_device_info
from .const import CONF_SELECTED_READERS, DOMAIN
from .coordinator import TechlanDataUpdateCoordinator


def configured_readers(config: dict[str, Any]) -> list[tuple[int, int]]:
    """Selected readers as a sorted ``[(pku, rd), ...]`` list."""
    return sorted(
        parse_reader_keys(config.get(CONF_SELECTED_READERS)),
        key=lambda item: (item[0], item[1]),
    )


def reader_facts(
    coordinator: TechlanDataUpdateCoordinator, pku: int, reader: int
) -> dict[str, Any]:
    """Polled facts for one reader (``{}`` while the first poll is pending)."""
    readers = (coordinator.data or {}).get("readers") or {}
    return readers.get(reader_key(pku, reader)) or {}


def reader_label(pku: int, reader: int, facts: dict[str, Any]) -> str:
    """Human-readable reader name (description from ServerSkif when available)."""
    description = str(facts.get("description") or "").strip()
    if description:
        return description
    device, number = decode_reader(reader)
    return f"Считыватель ПКУ {pku} · прибор {device} · считыватель {number}"


def reader_device_info(coordinator: TechlanDataUpdateCoordinator, pku: int) -> dict:
    """Child PKU device (the same device the climate sensors attach to)."""
    return build_device_info(
        identifiers={(DOMAIN, f"pku_{pku}")},
        name=f"Скиф ПКУ {pku}",
        model="ServerSkif PKU",
        configuration_url=coordinator.configuration_url,
        via_device_id=coordinator.parent_device_id,
        via_device=coordinator.parent_identifier,
    )


class TechlanReaderEntity:
    """Mixin with shared reader plumbing (unique id, name, device, control).

    Комбинируется с ``CoordinatorEntity``: класс-наследник вызывает
    ``CoordinatorEntity.__init__(coordinator)``, затем ``_init_reader(...)``.
    """

    _reader_entity_suffix = "reader"

    def _init_reader(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        reader: int,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._pku = int(pku)
        self._reader = int(reader)
        self._attr_unique_id = f"{DOMAIN}_{self._reader_entity_suffix}_{pku}_{reader}"
        self._attr_device_info = reader_device_info(coordinator, self._pku)

    @property
    def _facts(self) -> dict[str, Any]:
        return reader_facts(self._coordinator, self._pku, self._reader)

    def _reader_name(self) -> str:
        return reader_label(self._pku, self._reader, self._facts)

    def _reader_extra(self) -> dict[str, Any]:
        device, number = decode_reader(self._reader)
        return {
            "pku": self._pku,
            "reader": self._reader,
            "device": device,
            "reader_number": number,
            "state_code": self._facts.get("state"),
        }

    @property
    def _reader_key(self) -> str:
        return reader_key(self._pku, self._reader)

    # --- control -------------------------------------------------------------

    async def _apply_program(self, program: str) -> None:
        """Send a ``controlReader`` program (see ``const.READER_PROGRAMS``)."""
        await self._coordinator.client.async_control_reader(
            self._pku, self._reader, program
        )


__all__ = [
    "TechlanReaderEntity",
    "configured_readers",
    "reader_facts",
    "reader_label",
]
