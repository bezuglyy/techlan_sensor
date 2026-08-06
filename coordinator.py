"""Data coordinator for Techlan ARM-OPS."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TechlanApiClient, TechlanApiError
from .const import CONF_ARM_ID, CONF_BASE_URL, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_SELECTED_LOOPS, CONF_WS_PATH, DEFAULT_SCAN_INTERVAL, DEFAULT_WS_PATH, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TechlanDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Fetch a read-only ARM snapshot for all PKUs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        data = {**entry.data, **entry.options}
        self.client = TechlanApiClient(
            data[CONF_BASE_URL],
            data[CONF_ARM_ID],
            data[CONF_PASSWORD],
            data.get(CONF_WS_PATH, DEFAULT_WS_PATH),
        )
        self.selected_loops = data.get(CONF_SELECTED_LOOPS)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
        )

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_fetch_snapshot(self.selected_loops)
        except TechlanApiError as exc:
            raise UpdateFailed(str(exc)) from exc
