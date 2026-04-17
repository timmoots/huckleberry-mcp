"""Daily summary resource: huckleberry://today/{child_uid}.

Aggregates today's diapers, sleep, feeds, and pumping into a single
compact summary — useful for "how many diapers today?" style prompts
without burning tool calls.
"""

from __future__ import annotations

from ..auth import get_api
from ..utils import default_timezone, today_range, to_local_iso
from ..tools.children import validate_child_uid


async def _build_summary(child_uid: str) -> str:
    api = await get_api()
    start, now = today_range()

    diapers = await api.list_diaper_intervals(child_uid, start, now)
    diaper_counts: dict[str, int] = {"pee": 0, "poo": 0, "both": 0, "dry": 0}
    for d in diapers:
        mode = getattr(d, "mode", None)
        if mode in diaper_counts:
            diaper_counts[mode] += 1
    diaper_total = sum(diaper_counts.values())
    diaper_detail = ", ".join(f"{v} {k}" for k, v in diaper_counts.items() if v)

    sleep = await api.list_sleep_intervals(child_uid, start, now)
    sleep_seconds = sum(int(getattr(s, "duration", 0) or 0) for s in sleep)
    sleep_h = sleep_seconds // 3600
    sleep_m = (sleep_seconds % 3600) // 60

    feeds = await api.list_feed_intervals(child_uid, start, now)
    feed_count = len(feeds)
    bottle_ml = 0.0
    for f in feeds:
        amt = getattr(f, "amount", None)
        units = getattr(f, "units", None)
        if amt is not None:
            if units == "oz":
                bottle_ml += float(amt) * 29.5735
            else:
                bottle_ml += float(amt)

    pumps = await api.list_pump_intervals(child_uid, start, now)
    pump_ml = 0.0
    for p in pumps:
        total = (
            getattr(p, "totalAmount", None)
            or (getattr(p, "leftAmount", 0) or 0) + (getattr(p, "rightAmount", 0) or 0)
        )
        units = getattr(p, "units", "ml")
        if total:
            pump_ml += float(total) * (29.5735 if units == "oz" else 1.0)

    tz = default_timezone().key
    lines = [
        f"Today ({start.date().isoformat()}, {tz}):",
        f"  Diapers: {diaper_total} total" + (f" — {diaper_detail}" if diaper_detail else ""),
        f"  Sleep: {sleep_h}h {sleep_m}m across {len(sleep)} sessions",
        f"  Feeds: {feed_count}" + (f" (bottle: {int(bottle_ml)}ml)" if bottle_ml else ""),
    ]
    if pumps:
        lines.append(f"  Pumped: {int(pump_ml)}ml across {len(pumps)} sessions")
    lines.append(f"  As of: {to_local_iso(now)}")
    return "\n".join(lines)


def register_daily_summary(mcp):
    """Register the huckleberry://today/{child_uid} resource."""

    @mcp.resource("huckleberry://today/{child_uid}")
    async def today(child_uid: str) -> str:
        """Today's totals: diapers (by type), sleep (hours + sessions), feeds, pump volume."""
        resolved = await validate_child_uid(child_uid)
        return await _build_summary(resolved)
