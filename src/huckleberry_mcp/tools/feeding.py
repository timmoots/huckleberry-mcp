"""Feeding tools: nursing, bottle feeding, pumping.

Timezone contract: naive datetimes are interpreted as America/New_York
(EST/EDT). Override with HUCKLEBERRY_TIMEZONE.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ..auth import get_api
from ..utils import parse_dt, to_local_iso
from .children import validate_child_uid


async def log_bottle_feeding(
    child_uid: str | None = None,
    *,
    amount: float,
    bottle_type: str = "Formula",
    units: str = "ml",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Log a bottle feed.

    Args:
        child_uid: Optional; defaults to HUCKLEBERRY_DEFAULT_CHILD_UID.
        amount: Volume fed (positive number).
        bottle_type: "Formula", "Breast Milk", or "Mixed".
        units: "ml" or "oz". Defaults to ml.
        timestamp: Optional ISO datetime. Naive inputs treated as
                   America/New_York. Defaults to now.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")
    if bottle_type not in {"Formula", "Breast Milk", "Mixed"}:
        raise ValueError(f"Invalid bottle_type '{bottle_type}'.")
    if units not in {"ml", "oz"}:
        raise ValueError(f"Invalid units '{units}'.")

    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    start_time = parse_dt(timestamp)

    await api.log_bottle(
        child_uid,
        start_time=start_time,
        amount=amount,
        bottle_type=bottle_type,
        units=units,
    )
    return {
        "success": True,
        "message": f"Logged {amount}{units} of {bottle_type}",
        "amount": amount,
        "units": units,
        "bottle_type": bottle_type,
        "timestamp": to_local_iso(start_time),
    }


async def log_breastfeeding(
    child_uid: str | None = None,
    *,
    start_time: str,
    end_time: str | None = None,
    left_duration_minutes: int | None = None,
    right_duration_minutes: int | None = None,
    last_side: str = "left",
) -> dict[str, Any]:
    """Retroactively log a breastfeeding session.

    Provide EITHER end_time OR (left_duration_minutes + right_duration_minutes).

    Args:
        child_uid: Optional; defaults to HUCKLEBERRY_DEFAULT_CHILD_UID.
        start_time: ISO datetime of session start (interpreted in local TZ
                    if naive).
        end_time: Optional ISO datetime for session end.
        left_duration_minutes / right_duration_minutes: Optional per-side minutes.
        last_side: "left" or "right" (default "left").
    """
    if last_side not in {"left", "right"}:
        raise ValueError("last_side must be 'left' or 'right'")

    child_uid = await validate_child_uid(child_uid)
    api = await get_api()

    start_dt = parse_dt(start_time, default_now=False)
    if end_time:
        end_dt = parse_dt(end_time, default_now=False)
    elif left_duration_minutes is not None or right_duration_minutes is not None:
        total_min = (left_duration_minutes or 0) + (right_duration_minutes or 0)
        end_dt = start_dt + timedelta(minutes=total_min)
    else:
        raise ValueError("Provide end_time OR left/right_duration_minutes")

    left_sec = (left_duration_minutes or 0) * 60
    right_sec = (right_duration_minutes or 0) * 60

    await api.log_nursing(
        child_uid,
        start_time=start_dt,
        end_time=end_dt,
        side=last_side,
        left_duration=left_sec or None,
        right_duration=right_sec or None,
    )
    total = (end_dt - start_dt).total_seconds() / 60
    return {
        "success": True,
        "message": f"Logged {int(total)} min breastfeeding",
        "start_time": to_local_iso(start_dt),
        "end_time": to_local_iso(end_dt),
        "total_duration_minutes": int(total),
        "last_side": last_side,
    }


async def start_breastfeeding(
    child_uid: str | None = None,
    *,
    side: str = "left",
) -> dict[str, Any]:
    """Start a nursing timer on `side` ("left" or "right")."""
    if side not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.start_nursing(child_uid, side=side)
    return {"success": True, "message": f"Started nursing on {side}", "side": side}


async def pause_feeding(child_uid: str | None = None) -> dict[str, Any]:
    """Pause a running nursing timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.pause_nursing(child_uid)
    return {"success": True, "message": "Paused nursing"}


async def resume_feeding(child_uid: str | None = None) -> dict[str, Any]:
    """Resume a paused nursing timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.resume_nursing(child_uid)
    return {"success": True, "message": "Resumed nursing"}


async def switch_feeding_side(child_uid: str | None = None) -> dict[str, Any]:
    """Switch to the other side during a running or paused nursing timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.switch_nursing_side(child_uid)
    return {"success": True, "message": "Switched nursing side"}


async def complete_feeding(child_uid: str | None = None) -> dict[str, Any]:
    """Complete and save an active nursing timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.complete_nursing(child_uid)
    return {"success": True, "message": "Completed nursing"}


async def cancel_feeding(child_uid: str | None = None) -> dict[str, Any]:
    """Cancel and discard an active nursing timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.cancel_nursing(child_uid)
    return {"success": True, "message": "Cancelled nursing"}


async def get_feeding_history(
    child_uid: str | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch feeding history (nursing + bottle)."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    end_dt = parse_dt(end_date)
    start_dt = parse_dt(start_date) if start_date else (end_dt - timedelta(days=7))
    intervals = await api.list_feed_intervals(child_uid, start_dt, end_dt)
    # Most recent first — item 0 is "the last feed".
    intervals = sorted(intervals, key=lambda iv: getattr(iv, "start", 0), reverse=True)
    return [
        {
            "timestamp": to_local_iso(iv.start) if hasattr(iv, "start") else None,
            "mode": getattr(iv, "mode", None),
            "left_duration_seconds": getattr(iv, "leftDuration", None),
            "right_duration_seconds": getattr(iv, "rightDuration", None),
            "amount": getattr(iv, "amount", None),
            "units": getattr(iv, "units", None),
            "bottle_type": getattr(iv, "bottleType", None),
        }
        for iv in intervals
    ]


def register_feeding_tools(mcp):
    mcp.tool()(log_bottle_feeding)
    mcp.tool()(log_breastfeeding)
    mcp.tool()(start_breastfeeding)
    mcp.tool()(pause_feeding)
    mcp.tool()(resume_feeding)
    mcp.tool()(switch_feeding_side)
    mcp.tool()(complete_feeding)
    mcp.tool()(cancel_feeding)
    mcp.tool()(get_feeding_history)
