"""Growth tracking tools: weight, height, head circumference."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from ..auth import get_api
from ..utils import parse_dt, to_local_iso
from .children import validate_child_uid


async def log_growth(
    child_uid: Optional[str] = None,
    *,
    weight: Optional[float] = None,
    height: Optional[float] = None,
    head: Optional[float] = None,
    units: str = "imperial",
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Log growth measurements. At least one of weight/height/head required.

    Args:
        units: "imperial" (lbs/in) or "metric" (kg/cm).
        timestamp: Optional ISO datetime. Naive inputs treated as America/New_York.
    """
    if units not in {"imperial", "metric"}:
        raise ValueError("units must be 'imperial' or 'metric'")
    if weight is None and height is None and head is None:
        raise ValueError("Provide at least one of weight, height, head")

    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    start_time = parse_dt(timestamp)

    await api.log_growth(
        child_uid,
        start_time=start_time,
        weight=weight,
        height=height,
        head=head,
        units=units,
    )
    return {
        "success": True,
        "message": "Logged growth measurements",
        "weight": weight,
        "height": height,
        "head": head,
        "units": units,
        "timestamp": to_local_iso(start_time),
    }


async def get_latest_growth(child_uid: Optional[str] = None) -> dict[str, Any]:
    """Get the most recent growth record."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    latest = await api.get_latest_growth(child_uid)
    if latest is None:
        return {"message": "No growth measurements found"}
    return {
        "weight": getattr(latest, "weight", None),
        "height": getattr(latest, "height", None),
        "head": getattr(latest, "head", None),
        "weight_units": getattr(latest, "weightUnits", None),
        "height_units": getattr(latest, "heightUnits", None),
        "head_units": getattr(latest, "headUnits", None),
    }


async def get_growth_history(
    child_uid: Optional[str] = None,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch growth history (default last 30 days)."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    end_dt = parse_dt(end_date)
    start_dt = parse_dt(start_date) if start_date else (end_dt - timedelta(days=30))
    entries = await api.list_health_entries(child_uid, start_dt, end_dt)
    return [
        {
            "timestamp": to_local_iso(entry.start) if hasattr(entry, "start") else None,
            "weight": getattr(entry, "weight", None),
            "height": getattr(entry, "height", None),
            "head": getattr(entry, "head", None),
        }
        for entry in entries
    ]


def register_growth_tools(mcp):
    mcp.tool()(log_growth)
    mcp.tool()(get_latest_growth)
    mcp.tool()(get_growth_history)
