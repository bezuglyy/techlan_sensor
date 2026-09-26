"""Устройство HA на каждый ПРИБОР ServerSkif (чтобы не было «свалки»).

Раньше реле и считыватели всех приборов висели на одном устройстве пульта
(«Скиф ПКУ N»). Теперь на каждый прибор создаётся отдельное устройство-хаб под
родительским устройством пульта::

    SecurARM Sensor → Скиф ПКУ 1 → прибор 9 «ТД 1 Этаж» (С2000-2) → считыватели
                                  прибор 54 «Ворота КБИ» (С2000-2) → считыватели

Идентификатор прибора: ``("securarm_sensor", "pku_<pku>_dev_<device>")``.
"""

from __future__ import annotations

from typing import Any

from ._shared.shared_entities import async_resolve_device_id, build_device_info
from .const import DOMAIN


def pku_device_key(pku: int) -> tuple[str, str]:
    """Registry identifier of the PKU (пульт) device."""
    return (DOMAIN, f"pku_{int(pku)}")


def instrument_device_key(pku: int, device: int) -> tuple[str, str]:
    """Registry identifier of one instrument (прибор) of a PKU."""
    return (DOMAIN, f"pku_{int(pku)}_dev_{int(device)}")


def instrument_name(pku: int, device: int, facts: dict[str, Any] | None = None) -> str:
    """Human-readable instrument name: «ТД 1 Этаж · ПКУ 1 (С2000-2)»."""
    facts = facts or {}
    description = str(facts.get("device_description") or "").strip()
    device_type = str(facts.get("device_type") or "").strip()
    base = description or f"Прибор {int(device)}"
    name = f"{base} · ПКУ {int(pku)}"
    if device_type:
        name = f"{name} ({device_type})"
    return name


def instrument_device_info(
    coordinator: Any, pku: int, device: int, facts: dict[str, Any] | None = None
) -> dict[str, Any]:
    """DeviceInfo of the instrument device (child of the PKU device)."""
    facts = facts or {}
    device_type = str(facts.get("device_type") or "").strip()
    parent_identifier = pku_device_key(pku)
    return build_device_info(
        identifiers={instrument_device_key(pku, device)},
        name=instrument_name(pku, device, facts),
        model=device_type or "ServerSkif прибор",
        configuration_url=getattr(coordinator, "configuration_url", None),
        via_device_id=async_resolve_device_id(
            coordinator.hass, {parent_identifier}
        ),
        via_device=parent_identifier,
    )


__all__ = [
    "instrument_device_info",
    "instrument_device_key",
    "instrument_name",
    "pku_device_key",
]
