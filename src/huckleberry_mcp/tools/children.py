"""Child management tools."""

from __future__ import annotations

from typing import Any

from ..auth import get_api
from ..utils import resolve_child_uid


async def list_children() -> list[dict[str, Any]]:
    """List all child profiles on the Huckleberry account.

    Use this only if HUCKLEBERRY_DEFAULT_CHILD_UID is unset or when
    disambiguating between multiple children. Every other tool accepts
    an optional `child_uid` that defaults to the env var.
    """
    api = await get_api()
    user = await api.get_user()
    if user is None:
        return []
    out: list[dict[str, Any]] = []
    for ref in user.childList or []:
        cid = getattr(ref, "cid", None)
        if not cid:
            continue
        name = getattr(ref, "nickname", None)
        birth_date = None
        try:
            child = await api.get_child(cid)
            if child:
                name = name or getattr(child, "childsName", None)
                bd = getattr(child, "birthdate", None)
                if bd is not None:
                    birth_date = str(bd)
        except Exception:
            # non-fatal: still return what we have
            pass
        out.append({"uid": cid, "name": name, "birth_date": birth_date})
    return out


async def get_child_name(child_uid: str | None = None) -> str | None:
    """Get a child's display name.

    Args:
        child_uid: Optional; defaults to HUCKLEBERRY_DEFAULT_CHILD_UID.
    """
    child_uid = resolve_child_uid(child_uid)
    api = await get_api()
    user = await api.get_user()
    if user is None:
        return None
    for ref in user.childList or []:
        if getattr(ref, "cid", None) == child_uid:
            return getattr(ref, "nickname", None)
    return None


async def validate_child_uid(child_uid: str | None = None) -> str:
    """Resolve and validate a child_uid. Returns the concrete uid."""
    child_uid = resolve_child_uid(child_uid)
    api = await get_api()
    user = await api.get_user()
    if user is None:
        raise RuntimeError("Could not load Huckleberry user profile")
    valid = [getattr(r, "cid", None) for r in user.childList or []]
    if child_uid not in valid:
        raise ValueError(
            f"Invalid child_uid '{child_uid}'. Valid: {', '.join(str(v) for v in valid)}"
        )
    return child_uid


def register_children_tools(mcp):
    mcp.tool()(list_children)
    mcp.tool()(get_child_name)
