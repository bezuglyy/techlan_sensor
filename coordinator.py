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
    CONF_SELECTED_RELAYS,
    CONF_WS_PATH,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WS_PATH,
    DOMAIN,
)


class TechlanDataUpdateCoordinator(TechlanBaseCoordinator):
    """Fetch a read-only ARM snapshot (climate/state) + relay states."""

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
            selected_relays=data.get(CONF_SELECTED_RELAYS),
            effective_options=data,
        )

    @property
    def relay_states(self) -> dict:
        """Relay state snapshot keyed by ``pku:rl`` (empty when none selected)."""
        return ((self.data or {}).get("relays")) or {}
