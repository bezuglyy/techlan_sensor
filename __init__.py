"""Native Home Assistant integration for Techlan ARM-OPS."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HomeAssistantError, ServiceCall

from .const import CONFIRM, DOMAIN, PLATFORMS
from .coordinator import TechlanDataUpdateCoordinator

type TechlanConfigEntry = ConfigEntry[TechlanDataUpdateCoordinator]


def _register_services(hass: HomeAssistant) -> None:
    """Register control services once for the integration domain."""
    if hass.services.has_service(DOMAIN, "arm_part"):
        return

    schema = vol.Schema({
        vol.Required("pku", description="Номер ПКУ"): vol.Coerce(int),
        vol.Required("part", description="Номер раздела"): vol.Coerce(int),
        vol.Required(CONFIRM, default=False, description="Подтверждение команды"): vol.Coerce(bool),
    })

    async def get_coordinator() -> TechlanDataUpdateCoordinator:
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime_data = getattr(entry, "runtime_data", None)
            if runtime_data is not None:
                return runtime_data
        raise HomeAssistantError("Интеграция Techlan ARM-OPS ещё не загружена")

    async def handle_arm(call: ServiceCall) -> None:
        if not call.data[CONFIRM]:
            raise HomeAssistantError("Для управления требуется confirm: true")
        coordinator = await get_coordinator()
        await coordinator.client.async_control_part("arm", call.data["pku"], call.data["part"])
        await coordinator.async_request_refresh()

    async def handle_disarm(call: ServiceCall) -> None:
        if not call.data[CONFIRM]:
            raise HomeAssistantError("Для управления требуется confirm: true")
        coordinator = await get_coordinator()
        await coordinator.client.async_control_part("disarm", call.data["pku"], call.data["part"])
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "arm_part", handle_arm, schema)
    hass.services.async_register(DOMAIN, "disarm_part", handle_disarm, schema)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Techlan ARM-OPS integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TechlanConfigEntry) -> bool:
    """Set up Techlan ARM-OPS from a config entry."""
    coordinator = TechlanDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: TechlanConfigEntry) -> None:
    """Reload the coordinator/entities after connection options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TechlanConfigEntry) -> bool:
    """Unload Techlan ARM-OPS."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
