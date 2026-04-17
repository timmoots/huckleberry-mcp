"""Pumping tools. New in this fork — wraps py-huckleberry-api's pump API."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from ..auth import get_api
from ..utils import parse_dt, to_local_iso
from .children import validate_child_uid


async def log_pumping(
    child_uid: Optional[str] = None,
    *,
    total_amount: Optional[float] = None,
    left_amount: Optional[float] = None,
    right_amount: Optional[float] = None,
    duration_minutes: Optional[float] = None,
    units: str = "ml",
    notes: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Log a pumping session.

    Provide total_amount OR a combination of left_amount / right_amount.
    Duration is optional. Times are interpreted in America/New_York
    (EST/EDT) unless an explicit offset is supplied.
    """
    if total_amount is None and left_amount is None and right_amount is None:
        raise ValueError("Provide total_amount, left_amount, or right_amount")
    if units not in {"ml", "oz"}:
        raise ValueError("units must be 'ml' or 'oz'")

    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    start_time = parse_dt(timestamp)

    duration_seconds = (
        float(duration_minutes) * 60 if duration_minutes is not None else None
    )

    await api.log_pump(
        child_uid,
        start_time=start_time,
        duration=duration_seconds,
        left_amount=left_amount,
        right_amount=right_amount,
        total_amount=total_amount,
        units=units,
        notes=notes,
    )

    total = total_amount or ((left_amount or 0) + (right_amount or 0)) or 0
    return {
        "success": True,
        "message": f"Logged {total}{units} pumped",
        "total_amount": total,
        "left_amount": left_amount,
        "right_amount": right_amount,
        "units": units,
        "duration_minutes": duration_minutes,
        "timestamp": to_local_iso(start_time),
    }


async def get_pumping_history(
    child_uid: Optional[str] = None,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch pumping history (default last 7 days)."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    end_dt = parse_dt(end_date)
    start_dt = parse_dt(start_date) if start_date else (end_dt - timedelta(days=7))
    intervals = await api.list_pump_intervals(child_uid, start_dt, end_dt)
    return [
        {
            "timestamp": to_local_iso(iv.start) if hasattr(iv, "start") else None,
            "left_amount": getattr(iv, "leftAmount", None),
            "right_amount": getattr(iv, "rightAmount", None),
            "total_amount": getattr(iv, "totalAmount", None),
            "units": getattr(iv, "units", None),
            "duration_seconds": getattr(iv, "duration", None),
            "notes": getattr(iv, "notes", None),
        }
        for iv in intervals
    ]


def register_pumping_tools(mcp):
    mcp.tool()(log_pumping)
    mcp.tool()(get_pumping_history)
