"""Config flow for native Techlan Sensor integration."""

from __future__ import annotations

import asyncio
import time

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.core import HomeAssistant

from .api import TechlanApiClient, TechlanApiError
from ._shared.shared_api import (
    CannotConnectError,
    format_loop_label,
    loop_key,
    parse_loop_keys,
    url_is_valid,
)
from .const import (
    CONF_ARM_ID,
    CONF_BASE_URL,
    CONF_HUMIDITY_LOOPS,
    CONF_HUMIDITY_OFFSET,
    CONF_HUMIDITY_SCALE,
    CONF_PASSWORD,
    CONF_RELAY_PROGRAM,
    CONF_RELAY_TIME,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_LOOPS,
    CONF_SELECTED_RELAYS,
    CONF_TEMPERATURE_ALARM_HIGH,
    CONF_TEMPERATURE_ALARM_LOW,
    CONF_TEMPERATURE_LOOPS,
    CONF_TEMPERATURE_OFFSET,
    CONF_TEMPERATURE_SCALE,
    CONF_WS_PATH,
    CONFIG_MINOR_VERSION,
    DEFAULT_ARM_ID,
    DEFAULT_BASE_URL,
    DEFAULT_HUMIDITY_OFFSET,
    DEFAULT_HUMIDITY_SCALE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TEMPERATURE_ALARM_HIGH,
    DEFAULT_TEMPERATURE_ALARM_LOW,
    DEFAULT_TEMPERATURE_OFFSET,
    DEFAULT_TEMPERATURE_SCALE,
    DEFAULT_WS_PATH,
    DOMAIN,
)

# Discovery of every loop (ШС) across all PKUs takes several seconds and
# returns thousands of entries. Cache the result briefly so that re-rendering
# the form (and switching between flow steps) is instant.
_LOOPS_CACHE: dict[str, tuple[float, list]] = {}
_LOOPS_TTL = 600


async def _discover_loops_cached(data: dict) -> list:
    """Return the discovered loops, reusing a recent result when possible.

    Пустой результат НЕ кэшируется: сразу после рестарта HA/ARM ServerSkif
    опрос может отдать пусто, и раньше это «залипало» на 10 минут, из-за чего
    в списке выбора шлейфов не было ни одной строки. Теперь делаем один
    повтор, а если и он пуст — сообщаем ошибку (шаг покажет её оператору).
    """
    key = "|".join(
        [
            str(data.get(CONF_BASE_URL, "")),
            str(data.get(CONF_ARM_ID, "")),
            str(data.get(CONF_PASSWORD, "")),
            str(data.get(CONF_WS_PATH, DEFAULT_WS_PATH)),
        ]
    )
    now = time.monotonic()
    hit = _LOOPS_CACHE.get(key)
    if hit and (now - hit[0]) < _LOOPS_TTL:
        return hit[1]

    loops: list = []
    last_error: Exception | None = None
    for attempt in (1, 2):
        client = _client_for(data)
        try:
            loops = await client.async_discover_loops()
        except TechlanApiError as exc:  # нет связи — попробуем ещё раз
            last_error = exc
            loops = []
        finally:
            try:
                await client.async_shutdown()
            except Exception:  # noqa: BLE001 - закрытие не критично
                pass
        if loops:
            break
        if attempt == 1:
            await asyncio.sleep(1.0)

    if loops:
        _LOOPS_CACHE[key] = (now, loops)
        return loops
    if last_error is not None:
        raise last_error
    raise TechlanApiError("ARM вернул пустой список шлейфов")


_RELAYS_CACHE: dict[str, tuple[float, list]] = {}
_PKUS_CACHE: dict[str, tuple[float, list]] = {}

# Поле фильтра ПКУ на шаге выбора реле (в entry.options не сохраняется).
RELAY_PKU_FIELD = "relay_pkus"
_RELAYS_TTL = 600


def _client_for(data: dict) -> TechlanApiClient:
    return TechlanApiClient(
        data[CONF_BASE_URL].rstrip("/"),
        data[CONF_ARM_ID],
        data[CONF_PASSWORD],
        data.get(CONF_WS_PATH, DEFAULT_WS_PATH),
    )


async def _list_pkus_cached(data: dict) -> list[int]:
    """Cheap PKU list (single request) for the relay PKU filter."""
    key = "|".join(
        [
            str(data.get(CONF_BASE_URL, "")),
            str(data.get(CONF_ARM_ID, "")),
            str(data.get(CONF_PASSWORD, "")),
            str(data.get(CONF_WS_PATH, DEFAULT_WS_PATH)),
        ]
    )
    now = time.monotonic()
    hit = _PKUS_CACHE.get(key)
    if hit and (now - hit[0]) < _RELAYS_TTL:
        return hit[1]
    client = _client_for(data)
    try:
        pkus = await client.async_list_pkus()
    finally:
        try:
            await client.async_shutdown()
        except Exception:  # noqa: BLE001
            pass
    if pkus:
        _PKUS_CACHE[key] = (now, pkus)
    return pkus


async def _discover_relays_cached(data: dict, pkus: list | None = None) -> list:
    """Return discovered relays (PKU -> device -> relay), cached briefly.

    Walking every PKU/device takes minutes on the real park, so the settings
    step always filters by PKU first and only those PKUs are walked.
    """
    wanted = sorted({int(item) for item in (pkus or [])})
    key = "|".join(
        [
            str(data.get(CONF_BASE_URL, "")),
            str(data.get(CONF_ARM_ID, "")),
            str(data.get(CONF_PASSWORD, "")),
            str(data.get(CONF_WS_PATH, DEFAULT_WS_PATH)),
            ",".join(str(item) for item in wanted),
        ]
    )
    now = time.monotonic()
    hit = _RELAYS_CACHE.get(key)
    if hit and (now - hit[0]) < _RELAYS_TTL:
        return hit[1]
    client = _client_for(data)
    try:
        relays = await client.async_discover_relays(wanted or None)
    finally:
        try:
            await client.async_shutdown()
        except Exception:  # noqa: BLE001
            pass
    if relays:  # пустой список не кэшируем — иначе «залипнет» на 10 минут
        _RELAYS_CACHE[key] = (now, relays)
    return relays


def _relay_options(relays: list) -> list[dict]:
    return [{"value": item["key"], "label": item["label"]} for item in relays]


def _pku_filter_options(pkus: list) -> list[dict]:
    return [{"value": str(pku), "label": f"ПКУ {pku}"} for pku in sorted(pkus)]


def _filter_relays(relays: list, pkus: list[str] | None) -> list:
    if not pkus:
        return relays
    wanted = {str(item) for item in pkus}
    return [item for item in relays if str(item["pku"]) in wanted]


def _pkus_from_relay_keys(keys: list[str]) -> list[str]:
    """Derive PKU numbers from stored relay keys like '20:1025'."""
    result: set[str] = set()
    for key in keys or []:
        parts = str(key).split(":")
        if len(parts) == 2:
            result.add(parts[0])
    return sorted(result)


def _pku_select_options(loops: list) -> list[dict]:
    """Build the PKU picker options (with loop counts) from discovered loops."""
    counts: dict[int, int] = {}
    for item in loops:
        pku = int(item["pku"])
        counts[pku] = counts.get(pku, 0) + 1
    return [
        {"value": str(pku), "label": f"ПКУ {pku} — шлейфов: {counts[pku]}"}
        for pku in sorted(counts)
    ]


def _filter_loops(loops: list, pkus: list[str] | None) -> list:
    """Keep only loops belonging to the selected PKUs (empty = all)."""
    if not pkus:
        return loops
    wanted = {int(p) for p in pkus}
    return [item for item in loops if int(item["pku"]) in wanted]


def _loop_options(loops: list) -> list[dict]:
    return [{"value": item["key"], "label": item["label"]} for item in loops]


def _fallback_loop_options(keys: list[str]) -> list[dict]:
    """Опции из уже сохранённых ключей — когда живой опрос не удался.

    Оператор видит свои текущие шлейфы (и может их снять/добавить вручную),
    а не пустой список.
    """
    options: list[dict] = []
    for pku, part, sh in sorted(parse_loop_keys(keys or [])):
        options.append(
            {
                "value": loop_key(pku, part, sh),
                "label": format_loop_label(pku, part, sh, None),
            }
        )
    return options


def _pkus_from_loop_keys(keys: list[str]) -> list[str]:
    """Derive the PKU numbers from stored loop keys like '24:26:612'."""
    result: set[str] = set()
    for key in keys or []:
        parts = str(key).split(":")
        if len(parts) == 3:
            result.add(parts[0])
    return sorted(result)


def _select(options: list[dict], default: list[str] | None = None):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _loop_schema(
    loops: list,
    selected: list[str] | None = None,
    temperature_selected: list[str] | None = None,
    humidity_selected: list[str] | None = None,
    temperature_scale: float = DEFAULT_TEMPERATURE_SCALE,
    temperature_offset: float = DEFAULT_TEMPERATURE_OFFSET,
    humidity_scale: float = DEFAULT_HUMIDITY_SCALE,
    humidity_offset: float = DEFAULT_HUMIDITY_OFFSET,
    temperature_alarm_low: float = DEFAULT_TEMPERATURE_ALARM_LOW,
    temperature_alarm_high: float = DEFAULT_TEMPERATURE_ALARM_HIGH,
):
    options = _loop_options(loops)
    return vol.Schema(
        {
            vol.Optional(CONF_SELECTED_LOOPS, default=selected or []): _select(options),
            vol.Optional(
                CONF_TEMPERATURE_LOOPS, default=temperature_selected or []
            ): _select(options),
            vol.Required(
                CONF_TEMPERATURE_SCALE, default=float(temperature_scale)
            ): vol.Coerce(float),
            vol.Required(
                CONF_TEMPERATURE_OFFSET, default=float(temperature_offset)
            ): vol.Coerce(float),
            vol.Required(
                CONF_TEMPERATURE_ALARM_LOW, default=float(temperature_alarm_low)
            ): vol.Coerce(float),
            vol.Required(
                CONF_TEMPERATURE_ALARM_HIGH, default=float(temperature_alarm_high)
            ): vol.Coerce(float),
            vol.Optional(CONF_HUMIDITY_LOOPS, default=humidity_selected or []): _select(
                options
            ),
            vol.Required(
                CONF_HUMIDITY_SCALE, default=float(humidity_scale)
            ): vol.Coerce(float),
            vol.Required(
                CONF_HUMIDITY_OFFSET, default=float(humidity_offset)
            ): vol.Coerce(float),
        }
    )


async def _safe_pkus(data: dict) -> list[int]:
    """PKU list for the relay filter; empty when the ARM is unreachable."""
    try:
        return await _list_pkus_cached(data)
    except TechlanApiError:
        return []


async def _validate(hass: HomeAssistant, data: dict[str, str]) -> None:
    if not url_is_valid(
        data.get(CONF_BASE_URL, ""), data.get(CONF_WS_PATH, DEFAULT_WS_PATH)
    ):
        raise CannotConnectError
    client = TechlanApiClient(
        data[CONF_BASE_URL].rstrip("/"),
        data[CONF_ARM_ID],
        data[CONF_PASSWORD],
        data.get(CONF_WS_PATH, DEFAULT_WS_PATH),
    )
    try:
        await client.async_validate()
    except TechlanApiError as exc:
        raise CannotConnectError from exc


class TechlanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup from Home Assistant UI."""

    VERSION = 1
    MINOR_VERSION = CONFIG_MINOR_VERSION

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
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
                return await self.async_step_select_pkus()

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Required(CONF_ARM_ID, default=DEFAULT_ARM_ID): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select_pkus(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        data = self._pending_data
        try:
            loops = await _discover_loops_cached(data)
        except TechlanApiError:
            return self.async_abort(reason="cannot_connect")
        if not loops:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            self._pending_pkus = list(user_input.get("pkus", []))
            return await self.async_step_select_loops()
        schema = vol.Schema(
            {
                vol.Optional("pkus", default=[]): _select(_pku_select_options(loops)),
            }
        )
        return self.async_show_form(step_id="select_pkus", data_schema=schema)

    async def async_step_select_loops(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        data = self._pending_data
        pkus = getattr(self, "_pending_pkus", [])
        try:
            loops = _filter_loops(await _discover_loops_cached(data), pkus)
        except TechlanApiError:
            return self.async_abort(reason="cannot_connect")
        if not loops:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            selected = set(user_input.get(CONF_SELECTED_LOOPS, []))
            temperature_selected = list(user_input.get(CONF_TEMPERATURE_LOOPS, []))
            humidity_selected = list(user_input.get(CONF_HUMIDITY_LOOPS, []))
            selected.update(temperature_selected)
            selected.update(humidity_selected)
            data[CONF_SELECTED_LOOPS] = sorted(selected)
            data[CONF_TEMPERATURE_LOOPS] = temperature_selected
            data[CONF_TEMPERATURE_SCALE] = float(
                user_input.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE)
            )
            data[CONF_TEMPERATURE_OFFSET] = float(
                user_input.get(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET)
            )
            data[CONF_HUMIDITY_LOOPS] = humidity_selected
            data[CONF_HUMIDITY_SCALE] = float(
                user_input.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE)
            )
            data[CONF_HUMIDITY_OFFSET] = float(
                user_input.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET)
            )
            data[CONF_TEMPERATURE_ALARM_LOW] = float(
                user_input.get(
                    CONF_TEMPERATURE_ALARM_LOW, DEFAULT_TEMPERATURE_ALARM_LOW
                )
            )
            data[CONF_TEMPERATURE_ALARM_HIGH] = float(
                user_input.get(
                    CONF_TEMPERATURE_ALARM_HIGH, DEFAULT_TEMPERATURE_ALARM_HIGH
                )
            )
            return self.async_create_entry(title="SecurARM Sensor", data=data)
        schema = _loop_schema(loops)
        return self.async_show_form(step_id="select_loops", data_schema=schema)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return TechlanOptionsFlow()


class TechlanOptionsFlow(config_entries.OptionsFlow):
    """Allow changing ARM connection parameters after setup.

    The loop picker is split into two steps (PKU filter -> loops) because the
    full list holds thousands of entries and the browser cannot render it.
    """

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        loops_error = False
        try:
            loops = await _discover_loops_cached(current)
        except TechlanApiError:
            loops = []
            loops_error = True
        if not loops:
            loops_error = True

        if user_input is not None:
            pending = {
                CONF_BASE_URL: user_input[CONF_BASE_URL].rstrip("/"),
                CONF_ARM_ID: user_input[CONF_ARM_ID].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD]
                or current.get(CONF_PASSWORD, ""),
                CONF_WS_PATH: "/" + user_input[CONF_WS_PATH].lstrip("/"),
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
            }
            if pending[CONF_SCAN_INTERVAL] < 5 or pending[CONF_SCAN_INTERVAL] > 3600:
                errors["base"] = "cannot_connect"
            else:
                try:
                    await _validate(self.hass, pending)
                except (CannotConnectError, ValueError, TypeError):
                    errors["base"] = "cannot_connect"
                else:
                    self._pending = {**current, **pending}
                    self._pending_pkus = list(user_input.get("pkus", []))
                    return await self.async_step_loops()

        default_pkus = _pkus_from_loop_keys(current.get(CONF_SELECTED_LOOPS, []))
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)
                ): str,
                vol.Required(
                    CONF_ARM_ID, default=current.get(CONF_ARM_ID, DEFAULT_ARM_ID)
                ): str,
                vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_WS_PATH, default=current.get(CONF_WS_PATH, DEFAULT_WS_PATH)
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                vol.Optional("pkus", default=default_pkus): _select(
                    _pku_select_options(loops)
                ),
            }
        )
        if loops_error and "base" not in errors:
            errors["base"] = "loops_unavailable"
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_loops(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        current = getattr(self, "_pending", None) or {
            **self.config_entry.data,
            **self.config_entry.options,
        }
        pkus = getattr(self, "_pending_pkus", None)
        if pkus is None:
            pkus = _pkus_from_loop_keys(current.get(CONF_SELECTED_LOOPS, []))
        loops_error = False
        try:
            loops = _filter_loops(await _discover_loops_cached(current), pkus)
        except TechlanApiError:
            loops = []
            loops_error = True
        if not loops:
            loops_error = True
            # Опрос не удался — показываем уже сохранённые шлейфы,
            # чтобы список не был пустым и настройки можно было сохранить.
            known = list(current.get(CONF_SELECTED_LOOPS, []))
            known += list(current.get(CONF_TEMPERATURE_LOOPS, []))
            known += list(current.get(CONF_HUMIDITY_LOOPS, []))
            fallback = _fallback_loop_options(known)
            if fallback:
                loops = [
                    {
                        "key": item["value"],
                        "pku": 0,
                        "part": 0,
                        "sh": 0,
                        "description": "",
                        "label": item["label"],
                    }
                    for item in fallback
                ]

        if user_input is not None:
            selected = set(
                user_input.get(
                    CONF_SELECTED_LOOPS, current.get(CONF_SELECTED_LOOPS, [])
                )
            )
            temperature_selected = list(
                user_input.get(
                    CONF_TEMPERATURE_LOOPS, current.get(CONF_TEMPERATURE_LOOPS, [])
                )
            )
            humidity_selected = list(
                user_input.get(
                    CONF_HUMIDITY_LOOPS, current.get(CONF_HUMIDITY_LOOPS, [])
                )
            )
            selected.update(temperature_selected)
            selected.update(humidity_selected)
            # The return value of an OptionsFlow is what Home Assistant
            # persists into entry.options.
            self._pending_loops = {
                CONF_BASE_URL: current[CONF_BASE_URL],
                CONF_ARM_ID: current[CONF_ARM_ID],
                CONF_PASSWORD: current[CONF_PASSWORD],
                CONF_WS_PATH: current[CONF_WS_PATH],
                CONF_SCAN_INTERVAL: current[CONF_SCAN_INTERVAL],
                CONF_SELECTED_LOOPS: sorted(selected),
                CONF_TEMPERATURE_LOOPS: temperature_selected,
                CONF_TEMPERATURE_SCALE: float(
                    user_input.get(
                        CONF_TEMPERATURE_SCALE,
                        current.get(
                            CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE
                        ),
                    )
                ),
                CONF_TEMPERATURE_OFFSET: float(
                    user_input.get(
                        CONF_TEMPERATURE_OFFSET,
                        current.get(
                            CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET
                        ),
                    )
                ),
                CONF_HUMIDITY_LOOPS: humidity_selected,
                CONF_HUMIDITY_SCALE: float(
                    user_input.get(
                        CONF_HUMIDITY_SCALE,
                        current.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE),
                    )
                ),
                CONF_HUMIDITY_OFFSET: float(
                    user_input.get(
                        CONF_HUMIDITY_OFFSET,
                        current.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET),
                    )
                ),
                CONF_TEMPERATURE_ALARM_LOW: float(
                    user_input.get(
                        CONF_TEMPERATURE_ALARM_LOW,
                        current.get(
                            CONF_TEMPERATURE_ALARM_LOW,
                            DEFAULT_TEMPERATURE_ALARM_LOW,
                        ),
                    )
                ),
                CONF_TEMPERATURE_ALARM_HIGH: float(
                    user_input.get(
                        CONF_TEMPERATURE_ALARM_HIGH,
                        current.get(
                            CONF_TEMPERATURE_ALARM_HIGH,
                            DEFAULT_TEMPERATURE_ALARM_HIGH,
                        ),
                    )
                ),
            }
            return await self.async_step_relays()

        schema = _loop_schema(
            loops,
            current.get(CONF_SELECTED_LOOPS, []),
            current.get(CONF_TEMPERATURE_LOOPS, []),
            current.get(CONF_HUMIDITY_LOOPS, []),
            current.get(CONF_TEMPERATURE_SCALE, DEFAULT_TEMPERATURE_SCALE),
            current.get(CONF_TEMPERATURE_OFFSET, DEFAULT_TEMPERATURE_OFFSET),
            current.get(CONF_HUMIDITY_SCALE, DEFAULT_HUMIDITY_SCALE),
            current.get(CONF_HUMIDITY_OFFSET, DEFAULT_HUMIDITY_OFFSET),
            current.get(CONF_TEMPERATURE_ALARM_LOW, DEFAULT_TEMPERATURE_ALARM_LOW),
            current.get(CONF_TEMPERATURE_ALARM_HIGH, DEFAULT_TEMPERATURE_ALARM_HIGH),
        )
        if loops_error:
            return self.async_show_form(
                step_id="loops",
                data_schema=schema,
                errors={"base": "loops_unavailable"},
            )
        return self.async_show_form(step_id="loops", data_schema=schema)

    async def async_step_relays(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Pick the relays to expose (filter by PKU, затем список реле).

        Полный инвентарь реле большой, поэтому шаг двухфазный: сначала оператор
        отмечает ПКУ, затем выбирает реле уже только этих ПКУ.
        """
        current = getattr(self, "_pending", None) or {
            **self.config_entry.data,
            **self.config_entry.options,
        }
        selected_pkus: list = []
        selected_relays: list = []
        if user_input is not None:
            selected_pkus = list(user_input.get(RELAY_PKU_FIELD, []) or [])
            selected_relays = list(user_input.get(CONF_SELECTED_RELAYS, []) or [])
            # Пустой фильтр ПКУ = «реле не нужны» — это осознанное сохранение.
            if selected_relays or not selected_pkus:
                loops_data = getattr(self, "_pending_loops", None) or {}
                return self.async_create_entry(
                    title="",
                    data={
                        **loops_data,
                        CONF_BASE_URL: current[CONF_BASE_URL],
                        CONF_ARM_ID: current[CONF_ARM_ID],
                        CONF_PASSWORD: current[CONF_PASSWORD],
                        CONF_WS_PATH: current[CONF_WS_PATH],
                        CONF_SCAN_INTERVAL: current[CONF_SCAN_INTERVAL],
                        CONF_SELECTED_RELAYS: sorted(set(selected_relays)),
                        # per-relay карты сохраняем, чтобы не потерять настройки
                        CONF_RELAY_TIME: current.get(CONF_RELAY_TIME, {}),
                        CONF_RELAY_PROGRAM: current.get(CONF_RELAY_PROGRAM, {}),
                    },
                )
        else:
            selected_pkus = _pkus_from_relay_keys(
                current.get(CONF_SELECTED_RELAYS, [])
            )

        relays: list = []
        if selected_pkus:
            try:
                relays = _filter_relays(
                    await _discover_relays_cached(current, selected_pkus),
                    selected_pkus,
                )
            except TechlanApiError:
                relays = []

        schema = vol.Schema(
            {
                vol.Optional(
                    RELAY_PKU_FIELD, default=selected_pkus
                ): _select(_pku_filter_options(await _safe_pkus(current))),
                vol.Optional(
                    CONF_SELECTED_RELAYS,
                    default=current.get(CONF_SELECTED_RELAYS, []),
                ): _select(_relay_options(relays)),
            }
        )
        return self.async_show_form(step_id="relays", data_schema=schema)
