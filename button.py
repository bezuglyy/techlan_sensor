"""Arm/disarm buttons for Techlan ARM-OPS sections."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TechlanDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: TechlanDataUpdateCoordinator = entry.runtime_data
    entities = []
    for pku, item in coordinator.data.get("pkus", {}).items():
        for part, details in item.get("parts", {}).items():
            entities.append(TechlanPartActionButton(coordinator, int(pku), int(part), details, "arm"))
            entities.append(TechlanPartActionButton(coordinator, int(pku), int(part), details, "disarm"))
    async_add_entities(entities)


class TechlanPartActionButton(CoordinatorEntity[TechlanDataUpdateCoordinator], ButtonEntity):
    """One explicit action button for one section."""

    def __init__(self, coordinator: TechlanDataUpdateCoordinator, pku: int, part: int, details: dict, action: str) -> None:
        super().__init__(coordinator)
        description = str(details.get("description") or "").strip()
        action_title = "Взять" if action == "arm" else "Снять"
        self._pku = pku
        self._part = part
        self._action = action
        self._attr_unique_id = f"{DOMAIN}_pku_{pku}_part_{part}_{action}"
        self._attr_name = f"{action_title} {pku}-{part}" + (f" — {description}" if description else "")
        self._attr_icon = "mdi:shield-plus-outline" if action == "arm" else "mdi:shield-minus-outline"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"pku_{pku}")},
            "name": f"Скиф ПКУ {pku}",
            "manufacturer": "Techlan",
            "model": "ServerSkif PKU",
            "via_device": (DOMAIN, "arm_ops"),
        }

    async def async_press(self) -> None:
        await self.coordinator.client.async_control_part(self._action, self._pku, self._part)
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        return {"pku": self._pku, "part": self._part, "action": self._action}
