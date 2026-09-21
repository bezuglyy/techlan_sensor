"""WebSocket-клиент ServerSkif через прокси ARM WebSocket (сенсоры).

Общая механика постоянного соединения/лимитов — в ``_shared/shared_api.py``
(канонический источник — ``tools/ha-shared/shared_api.py``).

``techlan_sensor`` — **только чтение**: клиент не умеет отправлять команды
управления (нет ``controlPart_*``). Помимо состояния разделов он читает АЦП
шлейфов (``getShADC``) и извлекает из ответа температуру/влажность.
"""

from __future__ import annotations

import time
from typing import Any

from ._shared.shared_api import (
    PersistentTechlanClient,
    TechlanApiError,
    extract_humidity,
    extract_temperature,
    format_loop_label,
    loop_key,
    parse_loop_keys,
    websocket_url,
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
        self, selected_loops: list[str] | None = None
    ) -> dict[str, Any]:
        """Fetch PKU/part/loop state over the persistent session."""
        return await self.async_run(self._fetch_snapshot_sync, selected_loops)

    def _fetch_snapshot_sync(
        self, selected_loops: list[str] | None = None
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
