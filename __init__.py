"""Native Home Assistant integration for Techlan Sensor.

Сенсоры состояния/климата (АЦП, температура, влажность), калибровка
(scale/offset/пороги) и — по решению пользователя от 22.09.2026 — **управление
реле** (управляемыми выходами ServerSkif): состояние, вкл/выкл, переключение,
программы (включая мигание и работу по времени), время.

Управление разделами (arm/disarm) по-прежнему живёт только в ``techlan_ops``.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ._shared.shared_entities import async_get_or_create_device, configuration_url
from .const import (
    CONF_BASE_URL,
    CONF_HUMIDITY_LOOPS,
    CONF_HUMIDITY_OFFSET,
    CONF_HUMIDITY_SCALE,
    CONF_RELAY_PROGRAM,
    CONF_RELAY_TIME,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_LOOPS,
    CONF_SELECTED_READERS,
    CONF_SELECTED_RELAYS,
    CONF_TEMPERATURE_ALARM_HIGH,
    CONF_TEMPERATURE_ALARM_LOW,
    CONF_TEMPERATURE_LOOPS,
    CONF_TEMPERATURE_OFFSET,
    CONF_TEMPERATURE_SCALE,
    CONF_WS_PATH,
    CONFIG_MINOR_VERSION,
    DEFAULT_HUMIDITY_OFFSET,
    DEFAULT_HUMIDITY_SCALE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TEMPERATURE_ALARM_HIGH,
    DEFAULT_TEMPERATURE_ALARM_LOW,
    DEFAULT_TEMPERATURE_OFFSET,
    DEFAULT_TEMPERATURE_SCALE,
    DEFAULT_WS_PATH,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
    INTEGRATION_VERSION,
    PARENT_IDENTIFIER,
    PLATFORMS,
)
from .coordinator import TechlanDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type TechlanConfigEntry = ConfigEntry[TechlanDataUpdateCoordinator]

# Ключи, добавленные после первой версии схемы (используются миграцией).
_MIGRATION_DEFAULTS: dict = {
    CONF_WS_PATH: DEFAULT_WS_PATH,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_SELECTED_LOOPS: [],
    CONF_TEMPERATURE_LOOPS: [],
    CONF_TEMPERATURE_SCALE: DEFAULT_TEMPERATURE_SCALE,
    CONF_TEMPERATURE_OFFSET: DEFAULT_TEMPERATURE_OFFSET,
    CONF_HUMIDITY_LOOPS: [],
    CONF_HUMIDITY_SCALE: DEFAULT_HUMIDITY_SCALE,
    CONF_HUMIDITY_OFFSET: DEFAULT_HUMIDITY_OFFSET,
    CONF_TEMPERATURE_ALARM_LOW: DEFAULT_TEMPERATURE_ALARM_LOW,
    CONF_TEMPERATURE_ALARM_HIGH: DEFAULT_TEMPERATURE_ALARM_HIGH,
    CONF_SELECTED_READERS: [],
    CONF_SELECTED_RELAYS: [],
    CONF_RELAY_TIME: {},
    CONF_RELAY_PROGRAM: {},
}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Techlan Sensor integration."""
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: TechlanConfigEntry) -> bool:
    """Migrate config entry schema (options get new keys with defaults)."""
    if entry.version > 1:
        # Unknown future schema — do not touch it.
        return False
    if entry.version == 1 and entry.minor_version < CONFIG_MINOR_VERSION:
        options = dict(entry.options)
        merged = {**entry.data, **entry.options}
        for key, default in _MIGRATION_DEFAULTS.items():
            if key not in merged:
                options[key] = default
        hass.config_entries.async_update_entry(
            entry, options=options, minor_version=CONFIG_MINOR_VERSION
        )
        _LOGGER.info(
            "Techlan Sensor migrated to minor version %s", CONFIG_MINOR_VERSION
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TechlanConfigEntry) -> bool:
    """Set up Techlan Sensor from a config entry."""
    coordinator = TechlanDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(coordinator.async_shutdown)
    _register_parent_device(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _register_parent_device(
    hass: HomeAssistant,
    entry: TechlanConfigEntry,
    coordinator: TechlanDataUpdateCoordinator,
) -> None:
    """Create the parent device before entities so via_device_id resolves."""
    base_url = {**entry.data, **entry.options}.get(CONF_BASE_URL, "")
    coordinator.parent_identifier = (DOMAIN, PARENT_IDENTIFIER)
    coordinator.configuration_url = configuration_url(base_url)
    parent = async_get_or_create_device(
        hass,
        entry,
        {coordinator.parent_identifier},
        name=DEVICE_NAME,
        model=DEVICE_MODEL,
        sw_version=INTEGRATION_VERSION,
        configuration_url=coordinator.configuration_url,
    )
    coordinator.parent_device_id = parent.id
    # Дочерние устройства пультов — родители приборов: создаём заранее, чтобы
    # via_device_id у приборов разрешался сразу.
    for pku in sorted((coordinator.data or {}).get("pkus", {}) or {}):
        async_get_or_create_device(
            hass,
            entry,
            {(DOMAIN, f"pku_{int(pku)}")},
            name=f"Скиф ПКУ {int(pku)}",
            model="ServerSkif PKU",
            configuration_url=coordinator.configuration_url,
            via_device_id=coordinator.parent_device_id,
            via_device=coordinator.parent_identifier,
        )


async def _async_update_listener(
    hass: HomeAssistant, entry: TechlanConfigEntry
) -> None:
    """Reload the coordinator/entities after connection options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TechlanConfigEntry) -> bool:
    """Unload Techlan Sensor and close the persistent connection."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        await coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
