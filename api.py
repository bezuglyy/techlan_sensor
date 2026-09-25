"""WebSocket-клиент ServerSkif через прокси ARM WebSocket (сенсоры + реле).

Общая механика постоянного соединения/лимитов — в ``_shared/shared_api.py``
(канонический источник — ``tools/ha-shared/shared_api.py``).

``techlan_sensor`` читает состояние разделов/шлейфов (АЦП, температура,
влажность) и — по решению пользователя от 22.09.2026 — управляет **реле**
(управляемыми выходами ServerSkif): программы, переключение, время, и —
по решению пользователя от 25.09.2026 — управляет **считывателями**
(контроллерами доступа, напр. С2000-2): открытие доступа, свободный проход,
запрет доступа.

Управление разделами (arm/disarm) по-прежнему живёт только в ``techlan_ops``.
"""

from __future__ import annotations

import time
from typing import Any

from ._shared.shared_api import (
    PersistentTechlanClient,
    TechlanApiError,
    decode_reader,
    decode_relay,
    extract_humidity,
    extract_temperature,
    format_loop_label,
    format_reader_label,
    format_relay_label,
    loop_key,
    parse_loop_keys,
    parse_reader_keys,
    parse_relay_keys,
    reader_key,
    relay_key,
    relay_time_units,
    websocket_url,
)
from ._shared.shared_const import (
    DEFAULT_READER_PROGRAM,
    DEFAULT_RELAY_TIME,
    READER_PROGRAMS,
    RELAY_PROGRAMS,
    RELAY_TIME_PROGRAMS,
)

__all__ = ["TechlanApiClient", "TechlanApiError", "websocket_url"]


class TechlanApiClient(PersistentTechlanClient):
    """Read-only ServerSkif API client for techlan_sensor."""

    # --- discovery (config flow selector) ------------------------------------

    async def async_discover_loops(self) -> list[dict[str, Any]]:
        """Discover loop (ШС) choices grouped by section for the HA selector."""
        return await self.async_run(self._discover_loops_sync)

    def _discover_loops_sync(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        pkus = [
            int(item) for item in (self.request_sync("getListPKU").get("ret") or [])
        ]
        for pku in pkus:
            parts = [
                int(item)
                for item in (
                    self.request_sync("getListParts", pku=pku).get("ret") or []
                )
            ]
            for part in parts:
                shs = [
                    int(item)
                    for item in (
                        self.request_sync(
                            "getListPartSh", pku=pku, extra={"req": part}
                        ).get("ret")
                        or []
                    )
                ]
                descriptions: list[str] = []
                if shs:
                    descriptions = [
                        str(item)
                        for item in (
                            self.request_sync(
                                "getShDescription", pku=pku, extra={"req": shs}
                            ).get("ret")
                            or []
                        )
                    ]
                for sh, description in zip(shs, descriptions or [""] * len(shs)):
                    result.append(
                        {
                            "key": loop_key(pku, part, sh),
                            "pku": pku,
                            "part": part,
                            "sh": sh,
                            "description": description,
                            "label": format_loop_label(pku, part, sh, description),
                        }
                    )
        return result

    # --- snapshot -------------------------------------------------------------

    async def async_fetch_snapshot(
        self,
        selected_loops: list[str] | None = None,
        selected_relays: list[str] | None = None,
        selected_readers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch PKU/part/loop state (and relay/reader state) over the session."""
        return await self.async_run(
            self._fetch_snapshot_sync, selected_loops, selected_relays, selected_readers
        )

    def _fetch_snapshot_sync(
        self,
        selected_loops: list[str] | None = None,
        selected_relays: list[str] | None = None,
        selected_readers: list[str] | None = None,
    ) -> dict[str, Any]:
        pkus = [
            int(item) for item in (self.request_sync("getListPKU").get("ret") or [])
        ]
        if not pkus:
            raise TechlanApiError("ServerSkif returned no PKU")
        selected = None if selected_loops is None else parse_loop_keys(selected_loops)
        if selected is not None:
            pkus = sorted({pku for pku, _part, _sh in selected})
        parts: dict[int, list[int]] = {}
        descriptions: dict[tuple[int, int], str] = {}
        states: dict[int, dict[int, int]] = {pku: {} for pku in pkus}
        loops: dict[tuple[int, int], dict[int, dict[str, Any]]] = {}
        # Query one PKU at a time. ServerSkif emits unsolicited state messages,
        # so sequential requests avoid response interleaving.
        for pku in pkus:
            if selected is None:
                part_list = [
                    int(item)
                    for item in (
                        self.request_sync("getListParts", pku=pku).get("ret") or []
                    )
                ]
            else:
                part_list = sorted(
                    {
                        part
                        for selected_pku, part, _sh in selected
                        if selected_pku == pku
                    }
                )
            parts[pku] = part_list
            if part_list:
                description_message = self.request_sync(
                    "getPartDescription", pku=pku, extra={"req": part_list}
                )
                for part, description in zip(
                    part_list, description_message.get("ret") or []
                ):
                    descriptions[(pku, part)] = str(description)
                state_message = self.request_sync(
                    "getPartState", pku=pku, extra={"req": part_list}
                )
                states[pku] = {
                    part: int(state)
                    for part, state in zip(part_list, state_message.get("ret") or [])
                }
            if selected is not None:
                for part in part_list:
                    shs = sorted(
                        {
                            sh
                            for selected_pku, selected_part, sh in selected
                            if selected_pku == pku and selected_part == part
                        }
                    )
                    if not shs:
                        continue
                    sh_desc = (
                        self.request_sync(
                            "getShDescription", pku=pku, extra={"req": shs}
                        ).get("ret")
                        or []
                    )
                    sh_states = (
                        self.request_sync(
                            "getShState", pku=pku, extra={"req": shs}
                        ).get("ret")
                        or []
                    )
                    loop_data: dict[int, dict[str, Any]] = {}
                    for sh, desc, state in zip(shs, sh_desc, sh_states):
                        # ServerSkif expects the requested loop numbers in req
                        # (an array). The response contains sh, ret (raw ADC)
                        # and val (formatted resistance). ADC is best-effort.
                        adc_message = self._read_adc(pku, sh)
                        loop_data[sh] = {
                            "description": str(desc),
                            "state_code": int(state),
                            "adc": adc_message.get("ret"),
                            "adc_value": adc_message.get("val"),
                            "temperature": extract_temperature(adc_message),
                            "humidity": extract_humidity(adc_message),
                        }
                    loops[(pku, part)] = loop_data
        snapshot: dict[str, Any] = {
            "available": True,
            "pkus": {},
            "relays": self._read_relays_sync(selected_relays),
            "readers": self._read_readers_sync(selected_readers),
            "updated_at": time.time(),
        }
        for pku in pkus:
            snapshot["pkus"][pku] = {
                "part_count": len(parts.get(pku, [])),
                "parts": {
                    part: {
                        "description": descriptions.get((pku, part), ""),
                        "state_code": state,
                        "loops": loops.get((pku, part), {}),
                    }
                    for part, state in states.get(pku, {}).items()
                },
            }
        return snapshot

    # --- реле (управляемые выходы) -------------------------------------------

    async def async_discover_relays(
        self, pkus: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Discover relay choices (PKU -> device -> relay).

        ``pkus`` ограничивает обход выбранными пультами — полный инвентарь реле
        большой, поэтому настройки сначала спрашивают ПКУ, а затем обходят только
        их (иначе обход всех ПКУ/приборов занимает минуты).
        """
        return await self.async_run(self._discover_relays_sync, pkus)

    async def async_list_pkus(self) -> list[int]:
        """Cheap PKU list (for the settings selector)."""
        return await self.async_run(self._list_pkus_sync)

    def _list_pkus_sync(self) -> list[int]:
        return [
            int(item) for item in (self.request_sync("getListPKU").get("ret") or [])
        ]

    def _discover_relays_sync(
        self, pkus: list[int] | None = None
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        available = [
            int(item) for item in (self.request_sync("getListPKU").get("ret") or [])
        ]
        if pkus:
            wanted = {int(item) for item in pkus}
            pkus = [pku for pku in available if pku in wanted]
        else:
            pkus = available
        for pku in pkus:
            devices = [
                int(item)
                for item in (
                    self.request_sync("getListDevices", pku=pku).get("ret") or []
                )
            ]
            for device in devices:
                relays = [
                    int(item)
                    for item in (
                        self.request_sync(
                            "getListRelay", pku=pku, extra={"req": device}
                        ).get("ret")
                        or []
                    )
                ]
                if not relays:
                    continue
                descriptions = self._relay_descriptions(pku, relays)
                for relay, description in zip(relays, descriptions):
                    dev, number = decode_relay(relay)
                    result.append(
                        {
                            "key": relay_key(pku, relay),
                            "pku": pku,
                            "rl": relay,
                            "device": dev,
                            "relay": number,
                            "description": description,
                            "label": format_relay_label(pku, relay, description),
                        }
                    )
        return result

    def _relay_descriptions(self, pku: int, relays: list[int]) -> list[str]:
        """Best-effort relay descriptions (empty strings on timeout)."""
        try:
            return [
                str(item)
                for item in (
                    self.request_sync(
                        "getRelayDescription",
                        pku=pku,
                        extra={"req": relays},
                        teardown_on_timeout=False,
                    ).get("ret")
                    or []
                )
            ]
        except TechlanApiError:
            return []

    def _read_relays_sync(
        self, selected_relays: list[str] | None
    ) -> dict[str, dict[str, Any]]:
        """Read state/description for the configured relays (grouped by PKU)."""
        selected = parse_relay_keys(selected_relays)
        if not selected:
            return {}
        by_pku: dict[int, list[int]] = {}
        for pku, relay in selected:
            by_pku.setdefault(pku, []).append(relay)
        result: dict[str, dict[str, Any]] = {}
        for pku in sorted(by_pku):
            relays = sorted(set(by_pku[pku]))
            states = self._list_values("getRelayState", pku, relays)
            descriptions = self._relay_descriptions(pku, relays)
            for index, relay in enumerate(relays):
                dev, number = decode_relay(relay)
                state = states[index] if index < len(states) else None
                description = descriptions[index] if index < len(descriptions) else ""
                result[relay_key(pku, relay)] = {
                    "pku": pku,
                    "rl": relay,
                    "device": dev,
                    "relay": number,
                    "state": int(state) if state is not None else None,
                    "description": description,
                }
        return result

    def _list_values(self, funct: str, pku: int, items: list[int]) -> list[Any]:
        """Best-effort list read (empty list on timeout)."""
        try:
            return list(
                self.request_sync(
                    funct,
                    pku=pku,
                    extra={"req": items},
                    teardown_on_timeout=False,
                ).get("ret")
                or []
            )
        except TechlanApiError:
            return []

    async def async_control_relay(
        self,
        pku: int,
        relay: int,
        program: str = "on",
        *,
        time_seconds: float | None = None,
        mask: int | None = None,
        delay: int | None = None,
    ) -> None:
        """Apply a relay program (``controlRelay``).

        ``program`` — одно из имён ``RELAY_PROGRAMS`` (on/off/reset/on_time/
        off_time/blink_off/blink_on/blink_off_time/blink_on_time). Для программ
        из ``RELAY_TIME_PROGRAMS`` добавляется поле ``time`` (секунды переводятся
        в протокольные единицы 0.125 c).
        """
        code = RELAY_PROGRAMS.get(str(program))
        if code is None:
            raise TechlanApiError(f"unknown relay program: {program!r}")
        payload: dict[str, Any] = {
            "funct": "controlRelay",
            "pku": int(pku),
            "rl": int(relay),
            "prog": int(code),
        }
        if str(program) in RELAY_TIME_PROGRAMS:
            seconds = DEFAULT_RELAY_TIME if time_seconds is None else time_seconds
            payload["time"] = relay_time_units(seconds)
            if mask is not None:
                payload["mask"] = int(mask)
            if delay is not None:
                payload["delay"] = int(delay)
        await self.async_send_command(payload)

    async def async_invert_relay(self, pku: int, relay: int) -> None:
        """Toggle a relay (``controlRelay_Inv``)."""
        await self.async_send_command(
            {"funct": "controlRelay_Inv", "pku": int(pku), "rl": int(relay)}
        )

    # --- считыватели (контроллеры доступа, напр. С2000-2) --------------------

    async def async_discover_readers(
        self, pkus: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Discover reader choices (PKU -> device -> reader).

        Полный инвентарь большой, поэтому настройки сначала спрашивают ПКУ,
        а затем обходят только их (как и для реле).
        """
        return await self.async_run(self._discover_readers_sync, pkus)

    def _discover_readers_sync(
        self, pkus: list[int] | None = None
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        available = [
            int(item) for item in (self.request_sync("getListPKU").get("ret") or [])
        ]
        if pkus:
            wanted = {int(item) for item in pkus}
            pkus = [pku for pku in available if pku in wanted]
        else:
            pkus = available
        for pku in pkus:
            devices = [
                int(item)
                for item in (
                    self.request_sync("getListDevices", pku=pku).get("ret") or []
                )
            ]
            if not devices:
                continue
            # Описания/типы приборов — по одному запросу на ПКУ (дёшево), чтобы
            # в списке видеть «прибор 54 «Ворота КБИ» (С2000-2)».
            device_desc = self._list_text("getDeviceDescription", pku, devices)
            device_types = self._list_text("getDeviceTypeStr", pku, devices)
            for index, device in enumerate(devices):
                readers = [
                    int(item)
                    for item in (
                        self.request_sync(
                            "getListReader", pku=pku, extra={"req": device}
                        ).get("ret")
                        or []
                    )
                ]
                if not readers:
                    continue
                descriptions = self._reader_descriptions(pku, readers)
                desc = device_desc[index] if index < len(device_desc) else ""
                dtype = device_types[index] if index < len(device_types) else ""
                for reader, description in zip(readers, descriptions):
                    dev, number = decode_reader(reader)
                    result.append(
                        {
                            "key": reader_key(pku, reader),
                            "pku": pku,
                            "rd": reader,
                            "device": dev,
                            "reader": number,
                            "description": description,
                            "device_description": desc,
                            "device_type": dtype,
                            "label": format_reader_label(
                                pku, reader, description, desc, dtype
                            ),
                        }
                    )
        # Контроллеры ДОСТУПА (С2000-2) — в начало списка: остальные приборы тоже
        # отдают «считыватели» (нумерация как у реле), это шум для выбора.
        result.sort(
            key=lambda item: (
                "С2000-2" not in str(item.get("device_type") or ""),
                int(item["pku"]),
                int(item["device"]),
                int(item["reader"]),
            )
        )
        return result

    def _list_text(self, funct: str, pku: int, items: list[int]) -> list[str]:
        """Best-effort text list read (empty list on timeout)."""
        try:
            return [
                str(item)
                for item in (
                    self.request_sync(
                        funct,
                        pku=pku,
                        extra={"req": items},
                        teardown_on_timeout=False,
                    ).get("ret")
                    or []
                )
            ]
        except TechlanApiError:
            return []

    def _reader_descriptions(self, pku: int, readers: list[int]) -> list[str]:
        """Best-effort reader descriptions (empty strings on timeout)."""
        try:
            return [
                str(item)
                for item in (
                    self.request_sync(
                        "getReaderDescription",
                        pku=pku,
                        extra={"req": readers},
                        teardown_on_timeout=False,
                    ).get("ret")
                    or []
                )
            ]
        except TechlanApiError:
            return []

    def _read_readers_sync(
        self, selected_readers: list[str] | None
    ) -> dict[str, dict[str, Any]]:
        """Read state/description for the configured readers (grouped by PKU)."""
        selected = parse_reader_keys(selected_readers)
        if not selected:
            return {}
        by_pku: dict[int, list[int]] = {}
        for pku, reader in selected:
            by_pku.setdefault(pku, []).append(reader)
        result: dict[str, dict[str, Any]] = {}
        for pku in sorted(by_pku):
            readers = sorted(set(by_pku[pku]))
            states = self._list_values("getReaderState", pku, readers)
            descriptions = self._reader_descriptions(pku, readers)
            for index, reader in enumerate(readers):
                dev, number = decode_reader(reader)
                state = states[index] if index < len(states) else None
                description = descriptions[index] if index < len(descriptions) else ""
                result[reader_key(pku, reader)] = {
                    "pku": pku,
                    "rd": reader,
                    "device": dev,
                    "reader": number,
                    "state": int(state) if state is not None else None,
                    "description": description,
                }
        return result

    async def async_control_reader(
        self, pku: int, reader: int, program: str = DEFAULT_READER_PROGRAM
    ) -> None:
        """Apply a reader program (``controlReader``, Таблица А.4).

        ``program`` — одно из имён ``READER_PROGRAMS``: open (предоставление
        доступа), normal (разрешение доступа), unlock_reader/unlock_button,
        lock (запрет доступа), lock_reader/lock_button, free (открытие
        свободного доступа).
        """
        code = READER_PROGRAMS.get(str(program))
        if code is None:
            raise TechlanApiError(f"unknown reader program: {program!r}")
        await self.async_send_command(
            {
                "funct": "controlReader",
                "pku": int(pku),
                "rd": int(reader),
                "prog": int(code),
            }
        )

    def _read_adc(self, pku: int, sh: int) -> dict[str, Any]:
        """Read one ADC reply, tolerating absence (empty dict on timeout)."""
        try:
            return self.request_sync(
                "getShADC",
                pku=pku,
                sh=sh,
                extra={"req": [sh]},
                timeout=3.0,
                teardown_on_timeout=False,
            )
        except TechlanApiError:
            return {}

    async def async_validate(self) -> None:
        """Validate URL, authentication and at least one PKU."""
        await self.async_fetch_snapshot()
