"""Switch-сущности реле Techlan Sensor (включить/выключить).

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

from .const import RELAY_STATE_NAMES, RELAY_STATE_ON
from .coordinator import TechlanDataUpdateCoordinator
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


__all__ = ["TechlanRelaySwitch"]
