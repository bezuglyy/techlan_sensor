"""Small async WebSocket client for ServerSkif through ARM WebSocket proxy."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import websocket


class TechlanApiError(Exception):
    """Raised when ARM/ServerSkif cannot answer."""


def websocket_url(base_url: str, ws_path: str = "/skif-ws") -> str:
    """Convert the configured HTTP ARM URL to its WebSocket proxy URL."""
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/" + ws_path.lstrip("/"), "", "", ""))


class TechlanApiClient:
    """Read-only ServerSkif API client."""

    def __init__(self, base_url: str, arm_id: str, password: str, ws_path: str = "/skif-ws") -> None:
        self._url = websocket_url(base_url, ws_path)
        self._arm_id = arm_id
        self._password = password
        self._pending_messages: list[dict[str, Any]] = []

    async def async_discover_loops(self) -> list[dict[str, Any]]:
        """Discover loop (ШС) choices grouped by section for the HA selector."""
        return await asyncio.to_thread(self._discover_loops_sync)

    def _discover_loops_sync(self) -> list[dict[str, Any]]:
        self._pending_messages.clear()
        try:
            ws = websocket.create_connection(self._url, timeout=8, http_proxy_host=None, http_proxy_port=None)
            try:
                self._send(ws, {"funct": "armId", "id": self._arm_id, "pwd": self._password})
                if self._wait_for(ws, "armId").get("ret") is not True:
                    raise TechlanApiError("ServerSkif ARM authentication failed")
                self._send(ws, {"funct": "getListPKU"})
                pkus = [int(item) for item in (self._wait_for(ws, "getListPKU").get("ret") or [])]
                result: list[dict[str, Any]] = []
                for pku in pkus:
                    self._send(ws, {"funct": "getListParts", "pku": pku})
                    parts = [int(item) for item in (self._wait_for_pku(ws, "getListParts", pku).get("ret") or [])]
                    for part in parts:
                        self._send(ws, {"funct": "getListPartSh", "pku": pku, "req": part})
                        shs = [int(item) for item in (self._wait_for_pku(ws, "getListPartSh", pku).get("ret") or [])]
                        descriptions: list[str] = []
                        if shs:
                            self._send(ws, {"funct": "getShDescription", "pku": pku, "req": shs})
                            descriptions = [str(item) for item in (self._wait_for_pku(ws, "getShDescription", pku).get("ret") or [])]
                        for sh, description in zip(shs, descriptions or [""] * len(shs)):
                            result.append({
                                "key": f"{pku}:{part}:{sh}",
                                "pku": pku,
                                "part": part,
                                "sh": sh,
                                "description": description,
                                "label": f"ПКУ {pku} · раздел {part} · ШС {sh >> 8}/{sh & 0xFF} — {description or 'Без названия'}",
                            })
                return result
            finally:
                ws.close()
        except TechlanApiError:
            raise
        except Exception as exc:
            raise TechlanApiError(str(exc)) from exc

    async def async_fetch_snapshot(self, selected_loops: list[str] | None = None) -> dict[str, Any]:
        """Open one read-only session and fetch PKU/part state snapshot."""
        return await asyncio.to_thread(self._fetch_snapshot_sync, selected_loops)

    def _fetch_snapshot_sync(self, selected_loops: list[str] | None = None) -> dict[str, Any]:
        self._pending_messages.clear()
        try:
            ws = websocket.create_connection(self._url, timeout=8, http_proxy_host=None, http_proxy_port=None)
            try:
                self._send(ws, {"funct": "armId", "id": self._arm_id, "pwd": self._password})
                arm_result = self._wait_for(ws, "armId")
                if arm_result.get("ret") is not True:
                    raise TechlanApiError("ServerSkif ARM authentication failed")
                self._send(ws, {"funct": "getListPKU"})
                pku_result = self._wait_for(ws, "getListPKU")
                pkus = [int(item) for item in (pku_result.get("ret") or [])]
                if not pkus:
                    raise TechlanApiError("ServerSkif returned no PKU")
                selected = None if selected_loops is None else {
                    tuple(int(value) for value in item.split(":")) for item in selected_loops if len(item.split(":")) == 3
                }
                if selected is not None:
                    pkus = sorted({pku for pku, _part, _sh in selected})
                parts: dict[int, list[int]] = {}
                descriptions: dict[tuple[int, int], str] = {}
                states: dict[int, dict[int, int]] = {pku: {} for pku in pkus}
                loops: dict[tuple[int, int], dict[int, dict[str, Any]]] = {}
                # Query one PKU at a time. ServerSkif emits unsolicited state
                # messages, so sequential requests avoid response interleaving.
                for pku in pkus:
                    if selected is None:
                        self._send(ws, {"funct": "getListParts", "pku": pku})
                        part_list = [int(item) for item in (self._wait_for_pku(ws, "getListParts", pku).get("ret") or [])]
                    else:
                        part_list = sorted({part for selected_pku, part, _sh in selected if selected_pku == pku})
                    parts[pku] = part_list
                    if part_list:
                        self._send(ws, {"funct": "getPartDescription", "pku": pku, "req": part_list})
                        description_message = self._wait_for_pku(ws, "getPartDescription", pku)
                        for part, description in zip(part_list, description_message.get("ret") or []):
                            descriptions[(pku, part)] = str(description)
                        self._send(ws, {"funct": "getPartState", "pku": pku, "req": part_list})
                        state_message = self._wait_for_pku(ws, "getPartState", pku)
                        states[pku] = {part: int(state) for part, state in zip(part_list, state_message.get("ret") or [])}
                    if selected is not None:
                        for part in part_list:
                            shs = sorted({sh for selected_pku, selected_part, sh in selected if selected_pku == pku and selected_part == part})
                            if not shs:
                                continue
                            self._send(ws, {"funct": "getShDescription", "pku": pku, "req": shs})
                            sh_desc = self._wait_for_pku(ws, "getShDescription", pku).get("ret") or []
                            self._send(ws, {"funct": "getShState", "pku": pku, "req": shs})
                            sh_states = self._wait_for_pku(ws, "getShState", pku).get("ret") or []
                            loop_data = {}
                            for sh, desc, state in zip(shs, sh_desc, sh_states):
                                # ServerSkif expects the requested loop numbers
                                # in req (an array). The response contains sh,
                                # ret (raw ADC) and val (formatted resistance).
                                self._send(ws, {"funct": "getShADC", "pku": pku, "req": [sh]})
                                adc_message = self._wait_for_sh(ws, "getShADC", pku, sh)
                                loop_data[sh] = {
                                    "description": str(desc),
                                    "state_code": int(state),
                                    "adc": adc_message.get("ret"),
                                    "adc_value": adc_message.get("val"),
                                    "temperature": self._extract_temperature(adc_message),
                                    "humidity": self._extract_humidity(adc_message),
                                }
                            loops[(pku, part)] = loop_data
                snapshot = {"available": True, "pkus": {}, "updated_at": time.time()}
                for pku in pkus:
                    snapshot["pkus"][pku] = {"part_count": len(parts.get(pku, [])), "parts": {part: {"description": descriptions.get((pku, part), ""), "state_code": state, "loops": loops.get((pku, part), {})} for part, state in states.get(pku, {}).items()}}
                return snapshot
            finally:
                ws.close()
        except TechlanApiError:
            raise
        except Exception as exc:
            raise TechlanApiError(str(exc)) from exc

    @staticmethod
    def _extract_temperature(message: dict[str, Any]) -> float | None:
        """Extract a direct temperature only when ServerSkif labels it as °C."""
        value = message.get("temperature")
        if value is None:
            value = message.get("val")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if message.get("temperature") is not None else None
        text = str(value or "")
        if "°c" not in text.lower() and "град" not in text.lower():
            return None
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
        return float(match.group(0).replace(",", ".")) if match else None

    @staticmethod
    def _extract_humidity(message: dict[str, Any]) -> float | None:
        """Extract a direct humidity value only when ServerSkif labels it as percent."""
        value = message.get("humidity")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(message.get("val") or "")
        if "%" not in text and "влаж" not in text.lower():
            return None
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
        return float(match.group(0).replace(",", ".")) if match else None

    async def async_validate(self) -> None:
        """Validate URL, authentication and at least one PKU."""
        await self.async_fetch_snapshot()

    async def async_control_part(self, action: str, pku: int, part: int) -> None:
        """Send one protected arm/disarm command to a section."""
        if action not in {"arm", "disarm"}:
            raise TechlanApiError("Unsupported section control action")
        await asyncio.to_thread(self._control_part_sync, action, pku, part)

    def _control_part_sync(self, action: str, pku: int, part: int) -> None:
        command_name = "controlPart_Arm" if action == "arm" else "controlPart_DisArm"
        try:
            ws = websocket.create_connection(self._url, timeout=8, http_proxy_host=None, http_proxy_port=None)
            try:
                self._send(ws, {"funct": "armId", "id": self._arm_id, "pwd": self._password})
                if self._wait_for(ws, "armId").get("ret") is not True:
                    raise TechlanApiError("ServerSkif ARM authentication failed")
                # ServerSkif expects the operator authentication immediately
                # before the control command on the same WebSocket session.
                self._send(ws, {"funct": "userId", "pwd": self._password})
                if self._wait_for(ws, "userId").get("ret") is not True:
                    raise TechlanApiError("ServerSkif operator authentication failed")
                self._send(ws, {"funct": command_name, "pku": int(pku), "part": int(part)})
            finally:
                ws.close()
        except TechlanApiError:
            raise
        except Exception as exc:
            raise TechlanApiError(str(exc)) from exc

    def _send(self, ws: Any, payload: dict[str, Any]) -> None:
        ws.send(json.dumps(payload, ensure_ascii=False))

    def _wait_for(self, ws: Any, funct: str) -> dict[str, Any]:
        while True:
            message = self._receive(ws)
            if message.get("funct") == funct:
                return message

    def _wait_for_pku(self, ws: Any, funct: str, pku: int) -> dict[str, Any]:
        while True:
            message = self._receive(ws)
            if message.get("funct") == funct and int(message.get("pku", -1)) == pku:
                return message

    def _wait_for_sh(self, ws: Any, funct: str, pku: int, sh: int) -> dict[str, Any]:
        deadline = time.monotonic() + 3
        original_timeout = ws.gettimeout()
        while True:
            try:
                ws.settimeout(max(0.2, min(original_timeout or 3, deadline - time.monotonic())))
                message = self._receive(ws)
                if message.get("funct") == funct and int(message.get("pku", -1)) == pku and int(message.get("sh", -1)) == sh:
                    return message
                if time.monotonic() >= deadline:
                    return {}
            except Exception:
                return {}
            finally:
                ws.settimeout(original_timeout)

    def _receive(self, ws: Any) -> dict[str, Any]:
        if self._pending_messages:
            return self._pending_messages.pop(0)
        try:
            raw = ws.recv()
            decoder = json.JSONDecoder()
            offset = 0
            while offset < len(raw):
                while offset < len(raw) and raw[offset] not in "[{":
                    offset += 1
                if offset >= len(raw):
                    break
                try:
                    message, next_offset = decoder.raw_decode(raw, offset)
                except json.JSONDecodeError:
                    offset += 1
                    continue
                if isinstance(message, dict):
                    self._pending_messages.append(message)
                offset = next_offset
            if self._pending_messages:
                return self._pending_messages.pop(0)
            raise TechlanApiError("Empty message from ServerSkif")
        except json.JSONDecodeError as exc:
            raise TechlanApiError("Invalid JSON from ServerSkif") from exc
