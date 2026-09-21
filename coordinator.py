"""Data coordinator for Techlan Sensor (read-only)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ._shared.shared_coordinator import TechlanBaseCoordinator
from .api import TechlanApiClient
from .const import (
    CONF_ARM_ID,
    CONF_BASE_URL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_LOOPS,
    CONF_WS_PATH,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WS_PATH,
    DOMAIN,
)


class TechlanDataUpdateCoordinator(TechlanBaseCoordinator):
    """Fetch a read-only ARM snapshot for all PKUs (climate + state)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        data = {**entry.data, **entry.options}
        client = TechlanApiClient(
            data[CONF_BASE_URL],
            data[CONF_ARM_ID],
            data[CONF_PASSWORD],
            data.get(CONF_WS_PATH, DEFAULT_WS_PATH),
        )
        super().__init__(
            hass,
            entry,
            domain=DOMAIN,
            client=client,
            scan_interval=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            selected_loops=data.get(CONF_SELECTED_LOOPS),
            effective_options=data,
        )
