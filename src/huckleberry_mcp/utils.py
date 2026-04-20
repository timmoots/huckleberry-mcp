"""Shared utility functions for Huckleberry MCP server.

Timezone contract: naive ISO datetimes are interpreted as
America/New_York (EST/EDT) by default. Override with HUCKLEBERRY_TIMEZONE.
ISO strings with an explicit offset (e.g. "...+00:00" or "...Z") are
honored as-is.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
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


def parse_dt(
    value: str | datetime | None,
    *,
    default_now: bool = True,
    end_of_day: bool = False,
) -> datetime:
    """Parse an ISO datetime (or pass through datetime).

    - None + default_now=True -> current UTC time
    - Naive datetime -> localized to default timezone
    - String with 'Z' / offset -> honored as-is
    - Naive ISO string -> interpreted in default timezone

    If `end_of_day` is True and `value` is a date-only string (YYYY-MM-DD),
    the result is bumped to 23:59:59.999999 in the default timezone so
    history queries include events on that full day.
    """
    if value is None:
        if not default_now:
            raise ValueError("datetime is required")
        return datetime.now(UTC)
    date_only = isinstance(value, str) and len(value) == 10 and value.count("-") == 2
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_timezone())
    if end_of_day and date_only:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def to_local_iso(dt: datetime | float) -> str:
    """Format a datetime (or unix seconds) as ISO in the default timezone."""
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(float(dt), tz=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(default_timezone()).isoformat()


def today_range() -> tuple[datetime, datetime]:
    """Return (start_of_today, now) in the user's timezone."""
    tz = default_timezone()
    now_local = datetime.now(tz)
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now_local
