"""Общая база для relay-сущностей Techlan Sensor.

Реле ServerSkif — управляемые выходы, адресуемые парой ``(pku, rl)``, где
``rl = (device << 8) | relay_number``. Оператор выбирает нужные реле в настройках
(``CONF_SELECTED_RELAYS`` = ``["pku:rl", ...]``), после чего интеграция создаёт
набор сущностей на каждом реле:

* ``sensor``  — состояние (Включено / Выключено / Мигает);
* ``switch``  — включить/выключить (программы ``on``/``off``);
* ``button``  — переключить (``controlRelay_Inv``);
* ``select``  — программа (9 вариантов, включая мигание и работу по времени);
* ``number``  — время для программ ``*_time`` (секунды).

Источник данных — ``coordinator.data["relays"]`` (см. ``api._read_relays_sync``).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from ._shared.shared_api import decode_relay, parse_relay_keys, relay_key
from ._shared.shared_entities import build_device_info
from .const import (
    CONF_RELAY_PROGRAM,
    CONF_RELAY_TIME,
    CONF_SELECTED_RELAYS,
    DEFAULT_RELAY_PROGRAM,
    DEFAULT_RELAY_TIME,
    DOMAIN,
)
from .coordinator import TechlanDataUpdateCoordinator


def configured_relays(config: dict[str, Any]) -> list[tuple[int, int]]:
    """Selected relays as a sorted ``[(pku, rl), ...]`` list."""
    return sorted(
        parse_relay_keys(config.get(CONF_SELECTED_RELAYS)),
        key=lambda item: (item[0], item[1]),
    )


def relay_facts(
    coordinator: TechlanDataUpdateCoordinator, pku: int, relay: int
) -> dict[str, Any]:
    """Polled facts for one relay (``{}`` while the first poll is pending)."""
    relays = (coordinator.data or {}).get("relays") or {}
    return relays.get(relay_key(pku, relay)) or {}


def relay_label(pku: int, relay: int, facts: dict[str, Any]) -> str:
    """Human-readable relay name (description from ServerSkif when available)."""
    description = str(facts.get("description") or "").strip()
    if description:
        return description
    device, number = decode_relay(relay)
    return f"Реле ПКУ {pku} · прибор {device} · реле {number}"


def relay_device_info(coordinator: TechlanDataUpdateCoordinator, pku: int) -> dict:
    """Child PKU device (the same device the climate sensors attach to)."""
    return build_device_info(
        identifiers={(DOMAIN, f"pku_{pku}")},
        name=f"Скиф ПКУ {pku}",
        model="ServerSkif PKU",
        configuration_url=coordinator.configuration_url,
        via_device_id=coordinator.parent_device_id,
        via_device=coordinator.parent_identifier,
    )


class TechlanRelayEntity:
    """Mixin with shared relay plumbing (unique id, name, device, options).

    Комбинируется с ``CoordinatorEntity``: класс-наследник вызывает
    ``CoordinatorEntity.__init__(coordinator)``, затем ``_init_relay(...)``.
    """

    _relay_entity_suffix = "relay"

    def _init_relay(
        self,
        coordinator: TechlanDataUpdateCoordinator,
        entry: ConfigEntry,
        pku: int,
        relay: int,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._pku = int(pku)
        self._relay = int(relay)
        self._attr_unique_id = f"{DOMAIN}_{self._relay_entity_suffix}_{pku}_{relay}"
        self._attr_device_info = relay_device_info(coordinator, self._pku)

    @property
    def _facts(self) -> dict[str, Any]:
        return relay_facts(self._coordinator, self._pku, self._relay)

    def _relay_name(self) -> str:
        return relay_label(self._pku, self._relay, self._facts)

    def _relay_extra(self) -> dict[str, Any]:
        device, number = decode_relay(self._relay)
        return {
            "pku": self._pku,
            "relay": self._relay,
            "device": device,
            "relay_number": number,
            "state_code": self._facts.get("state"),
        }

    @property
    def _relay_key(self) -> str:
        return relay_key(self._pku, self._relay)

    # --- options-backed per-relay settings -----------------------------------

    def _option_map(self, key: str) -> dict[str, Any]:
        value = self._coordinator.option(key)
        return dict(value) if isinstance(value, dict) else {}

    async def _store_option_map(self, key: str, patch: dict[str, Any]) -> None:
        """Persist a ``{relay_key: value}`` map in entry options and apply live."""
        options: dict[str, Any] = {**self._entry.options}
        merged = self._option_map(key)
        merged.update(patch)
        options[key] = merged
        self.hass.config_entries.async_update_entry(self._entry, options=options)
        self._coordinator.update_runtime_options({**self._entry.data, **options})

    @property
    def relay_time(self) -> float:
        """Configured duration (seconds) for ``*_time`` programs."""
        stored = self._option_map(CONF_RELAY_TIME).get(self._relay_key)
        try:
            return float(stored)
        except (TypeError, ValueError):
            return DEFAULT_RELAY_TIME

    @property
    def relay_program(self) -> str:
        """Last program selected by the operator (for the ``select`` entity)."""
        stored = self._option_map(CONF_RELAY_PROGRAM).get(self._relay_key)
        return str(stored) if stored else DEFAULT_RELAY_PROGRAM

    # --- control -------------------------------------------------------------

    async def _apply_program(self, program: str) -> None:
        await self._coordinator.client.async_control_relay(
            self._pku,
            self._relay,
            program,
            time_seconds=self.relay_time,
        )
