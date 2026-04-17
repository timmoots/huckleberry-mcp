"""Shared utility functions for Huckleberry MCP server.

Timezone contract: naive ISO datetimes are interpreted as
America/New_York (EST/EDT) by default. Override with HUCKLEBERRY_TIMEZONE.
ISO strings with an explicit offset (e.g. "...+00:00" or "...Z") are
honored as-is.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def default_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("HUCKLEBERRY_TIMEZONE", "America/New_York"))


def resolve_child_uid(passed: str | None) -> str:
    """Return a concrete child_uid or raise.

    Falls back to HUCKLEBERRY_DEFAULT_CHILD_UID. Raises ValueError if
    neither source is available so the model can call list_children.
    """
    if passed:
        return passed
    default = os.getenv("HUCKLEBERRY_DEFAULT_CHILD_UID")
    if default:
        return default
    raise ValueError(
        "child_uid not provided and HUCKLEBERRY_DEFAULT_CHILD_UID is not set. "
        "Call list_children to get a uid, or configure the default env var."
    )


def parse_dt(value: str | datetime | None, *, default_now: bool = True) -> datetime:
    """Parse an ISO datetime (or pass through datetime).

    - None + default_now=True -> current UTC time
    - Naive datetime -> localized to default timezone
    - String with 'Z' / offset -> honored as-is
    - Naive ISO string -> interpreted in default timezone
    """
    if value is None:
        if not default_now:
            raise ValueError("datetime is required")
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_timezone())
    return dt


def to_local_iso(dt: datetime | float) -> str:
    """Format a datetime (or unix seconds) as ISO in the default timezone."""
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(float(dt), tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(default_timezone()).isoformat()


def today_range() -> tuple[datetime, datetime]:
    """Return (start_of_today, now) in the user's timezone."""
    tz = default_timezone()
    now_local = datetime.now(tz)
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now_local
