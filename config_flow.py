"""Config flow for native Techlan ARM-OPS integration."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.core import HomeAssistant

from .api import TechlanApiClient, TechlanApiError
from .const import CONF_ARM_ID, CONF_BASE_URL, CONF_HUMIDITY_LOOPS, CONF_HUMIDITY_OFFSET, CONF_HUMIDITY_SCALE, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_SELECTED_LOOPS, CONF_TEMPERATURE_LOOPS, CONF_TEMPERATURE_OFFSET, CONF_TEMPERATURE_SCALE, CONF_WS_PATH, DEFAULT_ARM_ID, DEFAULT_BASE_URL, DEFAULT_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_SCALE, DEFAULT_SCAN_INTERVAL, DEFAULT_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_SCALE, DEFAULT_WS_PATH, DOMAIN


@dataclass(frozen=True)
class CannotConnectError(Exception):
    """Unable to validate ARM connection."""


async def _validate(hass: HomeAssistant, data: dict[str, str]) -> None:
    parsed = urlparse(str(data.get(CONF_BASE_URL, "")).rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CannotConnectError
    if not str(data.get(CONF_WS_PATH, DEFAULT_WS_PATH)).startswith("/"):
        raise CannotConnectError
    client = TechlanApiClient(data[CONF_BASE_URL].rstrip("/"), data[CONF_ARM_ID], data[CONF_PASSWORD], data.get(CONF_WS_PATH, DEFAULT_WS_PATH))
    try:
        await client.async_validate()
    except TechlanApiError as exc:
        raise CannotConnectError from exc


class TechlanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup from Home Assistant UI."""

    VERSION = 1

    async def _loop_schema(self, data: dict, selected: list[str] | None = None, temperature_selected: list[str] | None = None, humidity_selected: list[str] | None = None):
        client = TechlanApiClient(data[CONF_BASE_URL], data[CONF_ARM_ID], data[CONF_PASSWORD], data.get(CONF_WS_PATH, DEFAULT_WS_PATH))
        loops = await client.async_discover_loops()
        options = [{"value": item["key"], "label": item["label"]} for item in loops]
        return vol.Schema({
            vol.Optional(CONF_SELECTED_LOOPS, default=selected or []): selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_TEMPERATURE_LOOPS, default=temperature_selected or []): selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_TEMPERATURE_SCALE, default=DEFAULT_TEMPERATURE_SCALE): vol.Coerce(float),
            vol.Required(CONF_TEMPERATURE_OFFSET, default=DEFAULT_TEMPERATURE_OFFSET): vol.Coerce(float),
            vol.Optional(CONF_HUMIDITY_LOOPS, default=humidity_selected or []): selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_HUMIDITY_SCALE, default=DEFAULT_HUMIDITY_SCALE): vol.Coerce(float),
            vol.Required(CONF_HUMIDITY_OFFSET, default=DEFAULT_HUMIDITY_OFFSET): vol.Coerce(float),
        })

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return TechlanOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_BASE_URL: user_input[CONF_BASE_URL].rstrip("/"),
                CONF_ARM_ID: user_input[CONF_ARM_ID].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            await self.async_set_unique_id(data[CONF_BASE_URL])
            self._abort_if_unique_id_configured()
            try:
                await _validate(self.hass, data)
            except (CannotConnectError, ValueError, TypeError):
                errors["base"] = "cannot_connect"
            else:
                self._pending_data = data
                return await self.async_step_select_loops()

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Required(CONF_ARM_ID, default=DEFAULT_ARM_ID): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select_loops(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        data = self._pending_data
        if user_input is not None:
            selected = set(user_input.get(CONF_SELECTED_LOOPS, []))
            temperature_selected = list(user_input.get(CONF_TEMPERATURE_LOOPS, []))
            humidity_selected = list(user_input.get(CONF_HUMIDITY_LOOPS, []))
            selected.update(temperature_selected)
            selected.update(humidity_selected)
            data[CONF_SELECTED_LOOPS] = sorted(selected)
            data[CONF_TEMPERATURE_LOOPS] = temperature_selected
            data[CONF_TEMPERATURE_SCALE] = float(user_input.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE))
            data[CONF_TEMPERATURE_OFFSET] = float(user_input.get(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET))
            data[CONF_HUMIDITY_LOOPS] = humidity_selected
            data[CONF_HUMIDITY_SCALE] = float(user_input.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE))
            data[CONF_HUMIDITY_OFFSET] = float(user_input.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET))
            return self.async_create_entry(title="Techlan Sensor", data=data)
        try:
            schema = await self._loop_schema(data)
        except TechlanApiError:
            return self.async_abort(reason="cannot_connect")
        return self.async_show_form(step_id="select_loops", data_schema=schema)


class TechlanOptionsFlow(config_entries.OptionsFlow):
    """Allow changing ARM connection parameters after setup."""

    async def _loop_schema(self, data: dict, selected: list[str] | None = None, temperature_selected: list[str] | None = None, humidity_selected: list[str] | None = None):
        client = TechlanApiClient(data[CONF_BASE_URL], data[CONF_ARM_ID], data[CONF_PASSWORD], data.get(CONF_WS_PATH, DEFAULT_WS_PATH))
        loops = await client.async_discover_loops()
        options = [{"value": item["key"], "label": item["label"]} for item in loops]
        return vol.Schema({
            vol.Optional(CONF_SELECTED_LOOPS, default=selected or []): selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_TEMPERATURE_LOOPS, default=temperature_selected or []): selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_TEMPERATURE_SCALE, default=float(data.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE))): vol.Coerce(float),
            vol.Required(CONF_TEMPERATURE_OFFSET, default=float(data.get(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET))): vol.Coerce(float),
            vol.Optional(CONF_HUMIDITY_LOOPS, default=humidity_selected or []): selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_HUMIDITY_SCALE, default=float(data.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE))): vol.Coerce(float),
            vol.Required(CONF_HUMIDITY_OFFSET, default=float(data.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET))): vol.Coerce(float),
        })

    async def async_step_init(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            selected = set(user_input.get(CONF_SELECTED_LOOPS, current.get(CONF_SELECTED_LOOPS, [])))
            temperature_selected = list(user_input.get(CONF_TEMPERATURE_LOOPS, current.get(CONF_TEMPERATURE_LOOPS, [])))
            humidity_selected = list(user_input.get(CONF_HUMIDITY_LOOPS, current.get(CONF_HUMIDITY_LOOPS, [])))
            selected.update(temperature_selected)
            selected.update(humidity_selected)
            data = {
                CONF_BASE_URL: user_input[CONF_BASE_URL].rstrip("/"),
                CONF_ARM_ID: user_input[CONF_ARM_ID].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD] or current.get(CONF_PASSWORD, ""),
                CONF_WS_PATH: "/" + user_input[CONF_WS_PATH].lstrip("/"),
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_SELECTED_LOOPS: sorted(selected),
                CONF_TEMPERATURE_LOOPS: temperature_selected,
                CONF_TEMPERATURE_SCALE: float(user_input.get(CONF_TEMPERATURE_SCALE, current.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE))),
                CONF_TEMPERATURE_OFFSET: float(user_input.get(CONF_TEMPERATURE_OFFSET, current.get(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET))),
                CONF_HUMIDITY_LOOPS: humidity_selected,
                CONF_HUMIDITY_SCALE: float(user_input.get(CONF_HUMIDITY_SCALE, current.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE))),
                CONF_HUMIDITY_OFFSET: float(user_input.get(CONF_HUMIDITY_OFFSET, current.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET))),
            }
            try:
                if data[CONF_SCAN_INTERVAL] < 5 or data[CONF_SCAN_INTERVAL] > 3600:
                    raise CannotConnectError
                await _validate(self.hass, data)
            except (CannotConnectError, ValueError, TypeError):
                errors["base"] = "cannot_connect"
            else:
                # The return value of an OptionsFlow is what Home Assistant
                # persists into entry.options. Updating the entry manually
                # and then returning an empty result caused HA to overwrite
                # the selected loops with {}.
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_BASE_URL: data[CONF_BASE_URL],
                        CONF_ARM_ID: data[CONF_ARM_ID],
                        CONF_PASSWORD: data[CONF_PASSWORD],
                        CONF_WS_PATH: data[CONF_WS_PATH],
                        CONF_SCAN_INTERVAL: data[CONF_SCAN_INTERVAL],
                        CONF_SELECTED_LOOPS: data[CONF_SELECTED_LOOPS],
                    },
                )

        try:
            loop_schema = await self._loop_schema(current, current.get(CONF_SELECTED_LOOPS, []), current.get(CONF_TEMPERATURE_LOOPS, []), current.get(CONF_HUMIDITY_LOOPS, []))
            loop_field = loop_schema.schema
        except TechlanApiError:
            loop_field = {vol.Optional(CONF_SELECTED_LOOPS, default=current.get(CONF_SELECTED_LOOPS, [])): selector.SelectSelector(selector.SelectSelectorConfig(options=[], multiple=True))}
        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Required(CONF_ARM_ID, default=current.get(CONF_ARM_ID, DEFAULT_ARM_ID)): str,
            vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Required(CONF_WS_PATH, default=current.get(CONF_WS_PATH, DEFAULT_WS_PATH)): str,
            vol.Required(CONF_SCAN_INTERVAL, default=int(current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
            **loop_field,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
