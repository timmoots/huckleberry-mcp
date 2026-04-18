"""Diaper tracking tools.

Timezone contract: naive `timestamp` values are interpreted in
America/New_York (EST/EDT) unless HUCKLEBERRY_TIMEZONE overrides.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from ..auth import get_api
from ..utils import parse_dt, to_local_iso
from .children import validate_child_uid

_VALID_MODES = {"pee", "poo", "both", "dry"}
_VALID_AMOUNTS = {"little", "medium", "big"}
_VALID_COLORS = {"yellow", "brown", "black", "green", "red", "gray"}
_VALID_CONSISTENCIES = {"solid", "loose", "runny", "mucousy", "hard", "pebbles", "diarrhea"}


async def log_diaper(
    child_uid: Optional[str] = None,
    *,
    mode: str,
    pee_amount: Optional[str] = None,
    poo_amount: Optional[str] = None,
    color: Optional[str] = None,
    consistency: Optional[str] = None,
    diaper_rash: bool = False,
    notes: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Log a diaper change.

    BEFORE CALLING THIS TOOL:
    - `mode` is required. Never assume it. Infer from the user's words when
      they're clear ("wet" -> "pee"; "poopy"/"dirty" -> "poo"; "soiled" or
      "#1 and #2" -> "both"; "clean"/"dry" -> "dry"). If the user just
      says "diaper" with no qualifier, ASK them: pee, poo, both, or dry?
    - When `mode` is "poo" or "both", ALWAYS ask the user to confirm
      poo_amount, color, and consistency before calling. These are
      diagnostically useful and the user expects the prompt. It is better
      to ask and log once than to log twice.
    - When `mode` is "pee" and the user volunteered amount, include it;
      don't ask unprompted for pee_amount — it adds friction without value.

    Args:
        child_uid: Optional; defaults to HUCKLEBERRY_DEFAULT_CHILD_UID.
        mode: REQUIRED. "pee", "poo", "both", or "dry".
        pee_amount / poo_amount: "little", "medium", or "big".
        color: "yellow", "brown", "black", "green", "red", or "gray".
        consistency: "solid", "loose", "runny", "mucousy", "hard", "pebbles",
                     or "diarrhea".
        diaper_rash: True if rash present.
        notes: Free text notes.
        timestamp: Optional ISO datetime for retroactive logging. Naive input
                   is interpreted as America/New_York. Defaults to now.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}")
    if pee_amount and pee_amount not in _VALID_AMOUNTS:
        raise ValueError(f"Invalid pee_amount '{pee_amount}'.")
    if poo_amount and poo_amount not in _VALID_AMOUNTS:
        raise ValueError(f"Invalid poo_amount '{poo_amount}'.")
    if color and color not in _VALID_COLORS:
        raise ValueError(f"Invalid color '{color}'.")
    if consistency and consistency not in _VALID_CONSISTENCIES:
        raise ValueError(f"Invalid consistency '{consistency}'.")

    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    start_time = parse_dt(timestamp)

    await api.log_diaper(
        child_uid,
        start_time=start_time,
        mode=mode,
        pee_amount=pee_amount,
        poo_amount=poo_amount,
        color=color,
        consistency=consistency,
        diaper_rash=diaper_rash,
        notes=notes,
    )

    return {
        "success": True,
        "message": f"Logged diaper change ({mode}) for child {child_uid}",
        "mode": mode,
        "color": color,
        "consistency": consistency,
        "timestamp": to_local_iso(start_time),
    }


async def get_diaper_history(
    child_uid: Optional[str] = None,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch diaper history.

    Args:
        child_uid: Optional; defaults to HUCKLEBERRY_DEFAULT_CHILD_UID.
        start_date: ISO date or datetime. Defaults to 7 days ago.
        end_date: ISO date or datetime. Defaults to now.
    """
    child_uid = await validate_child_uid(child_uid)
    api = await get_api()
    end_dt = parse_dt(end_date)
    start_dt = parse_dt(start_date) if start_date else (end_dt - timedelta(days=7))

    intervals = await api.list_diaper_intervals(child_uid, start_dt, end_dt)
    # Most recent first — item 0 is "the last diaper".
    intervals = sorted(intervals, key=lambda iv: getattr(iv, "start", 0), reverse=True)
    return [
        {
            "timestamp": to_local_iso(iv.start) if hasattr(iv, "start") else None,
            "mode": getattr(iv, "mode", None),
            "color": getattr(iv, "color", None),
            "consistency": getattr(iv, "consistency", None),
            "notes": getattr(iv, "notes", None),
        }
        for iv in intervals
    ]


def register_diaper_tools(mcp):
    mcp.tool()(log_diaper)
    mcp.tool()(get_diaper_history)
