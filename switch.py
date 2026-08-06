"""One arm/disarm switch per Techlan ARM-OPS section."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_STATE_CODES, DOMAIN, STATE_NAMES
from .coordinator import TechlanDataUpdateCoordinator

ARMED_CODES = {23, 24}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    entities = []
    for pku, item in coordinator.data.get("pkus", {}).items():
        for part, details in item.get("parts", {}).items():
            entities.append(TechlanPartSwitch(coordinator, int(pku), int(part), details))
    async_add_entities(entities)


class TechlanPartSwitch(CoordinatorEntity[TechlanDataUpdateCoordinator], SwitchEntity):
    """A single switch whose state reflects whether a section is armed."""

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, pku: int, part: int, details: dict) -> None:
        super().__init__(coordinator)
        description = str(details.get("description") or "").strip()
        self._pku = pku
        self._part = part
        self._description = description
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_control"
        self._attr_name = description or "Без названия"
        self._attr_icon = "mdi:shield-check-outline"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"pku_{pku}")},
            "name": f"Скиф ПКУ {pku}",
            "manufacturer": "Techlan",
            "model": "ServerSkif PKU",
            "via_device": (DOMAIN, "arm_ops"),
        }

    def _details(self) -> dict:
        return self.coordinator.data.get("pkus", {}).get(self._pku, {}).get("parts", {}).get(self._part, {})

    @property
    def is_on(self) -> bool:
        return int(self._details().get("state_code", -1)) in ARMED_CODES

    @property
    def icon(self) -> str:
        code = int(self._details().get("state_code", -1))
        if code in ALARM_STATE_CODES:
            return "mdi:shield-alert-outline"
        if code not in ARMED_CODES:
            return "mdi:shield-off-outline"
        return "mdi:shield-check-outline"

    @property
    def extra_state_attributes(self) -> dict:
        code = int(self._details().get("state_code", -1))
        return {
            "pku": self._pku,
            "part": self._part,
            "description": self._description,
            "state_code": code,
            "state_text": STATE_NAMES.get(code, f"Состояние {code}"),
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.async_control_part("arm", self._pku, self._part)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.async_control_part("disarm", self._pku, self._part)
        await self.coordinator.async_request_refresh()
