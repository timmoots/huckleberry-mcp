"""Sleep tracking tools: timer + retroactive logging + history."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ..auth import get_api
from ..utils import parse_dt, to_local_iso
from .children import validate_child_uid


async def log_sleep(
    child_uid: str | None = None,
    *,
    start_time: str,
    end_time: str | None = None,
    duration_minutes: int | None = None,
) -> dict[str, Any]:
    """Retroactively log a completed sleep session.

    Provide EITHER end_time OR duration_minutes.
    Times are interpreted in America/New_York (EST/EDT) unless the input
    carries an explicit offset.
    """
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()

    start_dt = parse_dt(start_time, default_now=False)
    if end_time and duration_minutes is not None:
        raise ValueError("Provide end_time OR duration_minutes, not both")
    if end_time:
        end_dt = parse_dt(end_time, default_now=False)
    elif duration_minutes is not None:
        end_dt = start_dt + timedelta(minutes=duration_minutes)
    else:
        raise ValueError("Provide end_time or duration_minutes")
    if end_dt <= start_dt:
        raise ValueError("end_time must be after start_time")

    await api.log_sleep(child_uid, start_time=start_dt, end_time=end_dt)
    total = int((end_dt - start_dt).total_seconds() / 60)
    return {
        "success": True,
        "message": f"Logged {total} min sleep",
        "start_time": to_local_iso(start_dt),
        "end_time": to_local_iso(end_dt),
        "duration_minutes": total,
    }


async def start_sleep(child_uid: str | None = None) -> dict[str, Any]:
    """Start a sleep timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.start_sleep(child_uid)
    return {"success": True, "message": "Started sleep timer"}


async def pause_sleep(child_uid: str | None = None) -> dict[str, Any]:
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.pause_sleep(child_uid)
    return {"success": True, "message": "Paused sleep timer"}


async def resume_sleep(child_uid: str | None = None) -> dict[str, Any]:
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.resume_sleep(child_uid)
    return {"success": True, "message": "Resumed sleep timer"}


async def complete_sleep(child_uid: str | None = None) -> dict[str, Any]:
    """Complete and save the active sleep timer."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.complete_sleep(child_uid)
    return {"success": True, "message": "Completed sleep"}


async def cancel_sleep(child_uid: str | None = None) -> dict[str, Any]:
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    await api.cancel_sleep(child_uid)
    return {"success": True, "message": "Cancelled sleep timer"}


async def get_sleep_history(
    child_uid: str | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch sleep history."""
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    end_dt = parse_dt(end_date, end_of_day=True)
    start_dt = parse_dt(start_date) if start_date else (end_dt - timedelta(days=7))
    intervals = await api.list_sleep_intervals(child_uid, start_dt, end_dt)
    # Most recent first — item 0 is "the last sleep".
    intervals = sorted(intervals, key=lambda iv: getattr(iv, "start", 0), reverse=True)
    out: list[dict[str, Any]] = []
    for iv in intervals:
        start = getattr(iv, "start", None)
        duration = getattr(iv, "duration", 0) or 0
        end = getattr(iv, "end", None)
        out.append(
            {
                "start_time": to_local_iso(start) if start is not None else None,
                "end_time": to_local_iso(end) if end is not None else None,
                "duration_minutes": int(duration // 60) if duration else 0,
            }
        )
    return out


def register_sleep_tools(mcp):
    mcp.tool()(log_sleep)
    mcp.tool()(start_sleep)
    mcp.tool()(pause_sleep)
    mcp.tool()(resume_sleep)
    mcp.tool()(complete_sleep)
    mcp.tool()(cancel_sleep)
    mcp.tool()(get_sleep_history)
