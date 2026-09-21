"""Diagnostics support for Techlan Sensor."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ._shared.shared_api import mask_url
from .const import CONF_BASE_URL, DOMAIN, INTEGRATION_VERSION

# Ключи, которые никогда не попадают в диагностический дамп.
TO_REDACT = {"password", "pwd", "token", "api_key", "ssh_pass", "secret"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return masked diagnostics for a config entry."""
    coordinator = getattr(entry, "runtime_data", None)
    data = getattr(coordinator, "data", None) or {}
    raw_url = str(entry.options.get(CONF_BASE_URL) or entry.data.get(CONF_BASE_URL, ""))
    pkus = data.get("pkus", {}) or {}
    loop_count = sum(
        len(part.get("loops", {}))
        for item in pkus.values()
        for part in item.get("parts", {}).values()
    )
    update_interval = getattr(coordinator, "update_interval", None)
    return {
        "entry": {
            "title": entry.title,
            "domain": DOMAIN,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "connection": {
            "base_url": mask_url(raw_url),
            "integration_version": INTEGRATION_VERSION,
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "update_interval_seconds": (
                update_interval.total_seconds() if update_interval else None
            ),
            "parent_device_id": getattr(coordinator, "parent_device_id", None),
        },
        "calibration": {
            "temperature_scale": entry.options.get("temperature_scale"),
            "temperature_offset": entry.options.get("temperature_offset"),
            "humidity_scale": entry.options.get("humidity_scale"),
            "humidity_offset": entry.options.get("humidity_offset"),
            "temperature_alarm_low": entry.options.get("temperature_alarm_low"),
            "temperature_alarm_high": entry.options.get("temperature_alarm_high"),
        },
        "snapshot": {
            "available": data.get("available"),
            "updated_at": data.get("updated_at"),
            "pku_count": len(pkus),
            "loop_count": loop_count,
            "pkus": {
                str(pku): {"part_count": item.get("part_count", 0)}
                for pku, item in pkus.items()
            },
        },
    }
