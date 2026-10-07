"""Shrink tool results for the model's context window.

This only affects what the *model* sees. The full, uncompacted result always
goes into `tool_calls`, because that log is what gets graded.

Worth doing: a single GMAIL_FETCH_EMAILS returns the full Gmail API envelope
with base64 bodies and a headers array per message. Projecting it to the fields
a human would quote cuts roughly an order of magnitude off the context and, just
as usefully, stops the model from quoting an internalDate at the user.
"""

from __future__ import annotations

import json
from typing import Any

from backend.helpers import config

# Result keys that hold the interesting list, in the order we look for them.
_LIST_KEYS = (
    "messages", "conversations", "issues", "events", "items", "files", "threads",
    "users", "teams", "projects", "comments", "drafts", "labels", "channels",
    "pull_requests", "commits", "branches", "releases", "notifications", "results",
)


def _headers_to_fields(message: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Gmail payload.headers array into plain fields."""
    out: dict[str, Any] = {}
    payload = message.get("payload") or {}
    for header in payload.get("headers") or []:
        name = str(header.get("name", "")).lower()
        if name in ("from", "to", "cc", "subject", "date"):
            out[name] = header.get("value")
    return out


def _project_gmail(message: dict[str, Any]) -> dict[str, Any]:
    projected = {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "labelIds": message.get("labelIds"),
        "snippet": message.get("snippet"),
    }
    projected.update(_headers_to_fields(message))
    payload = message.get("payload") or {}
    body = (payload.get("body") or {}).get("data")
    if isinstance(body, str) and body:
        projected["body"] = body[:600]
    return {k: v for k, v in projected.items() if v not in (None, [], "")}


def _shrink_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    if "payload" in item and "labelIds" in item:  # a Gmail message
        return _project_gmail(item)
    # Generic: drop bulky, low-signal subtrees.
    return {
        k: v
        for k, v in item.items()
        if k not in ("payload", "raw", "historyId", "sizeEstimate", "body_html", "avatarUrl")
    }


def compact(result: Any) -> Any:
    """Return a context-sized view of a tool result."""
    if isinstance(result, dict):
        out = dict(result)
        for key in _LIST_KEYS:
            value = out.get(key)
            if isinstance(value, list) and value:
                shown = [_shrink_item(v) for v in value[: config.MAX_LIST_ITEMS_IN_CONTEXT]]
                hidden = len(value) - len(shown)
                out[key] = shown
                if hidden > 0:
                    out[f"_{key}_omitted"] = f"{hidden} more not shown"
        result = out

    encoded = json.dumps(result, default=str)
    if len(encoded) <= config.MAX_TOOL_RESULT_CHARS:
        return result
    return {
        "_truncated": True,
        "_note": f"Result was {len(encoded)} chars; showing the first {config.MAX_TOOL_RESULT_CHARS}.",
        "preview": encoded[: config.MAX_TOOL_RESULT_CHARS],
    }


def to_tool_message(result: Any, error: str | None) -> str:
    """Serialise a tool outcome for the model."""
    if error:
        return json.dumps({"ok": False, "error": error}, default=str)
    return json.dumps({"ok": True, "result": compact(result)}, default=str)
