"""Static tool index, built once at import.

Wraps the registry in `backend.main` with the cluster taxonomy so the router can
work in terms of clusters and the executor can look a tool up in O(1).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from backend.helpers.clusters import CLUSTERS, CLUSTERS_BY_ID, TOOL_HINTS, Cluster

# Read-only prefixes. Used to decide what may run concurrently and what counts
# as a mutation for the write-safety policy.
_READ_VERBS = (
    "list", "get", "find", "fetch", "search", "read", "download", "health",
    "token_status", "instances", "free_busy", "current_date", "settings_list",
    "generate_ids", "profile", "contacts", "people", "me", "tree", "logs",
)
_WRITE_VERBS = (
    "create", "update", "patch", "delete", "send", "reply", "add", "remove",
    "move", "trash", "merge", "insert", "write", "modify", "star", "unstar",
    "fork", "push", "clear", "duplicate", "empty", "dismiss", "mark", "manage",
    "trigger", "assign", "request", "run", "sync", "watch", "triage", "edit",
    "copy", "share", "label", "subscribe",
)


@dataclass(frozen=True)
class ToolInfo:
    name: str
    service: str
    cluster: str
    description: str
    is_write: bool


def _classify(name: str) -> bool:
    """True when the tool mutates state.

    Deliberately conservative: anything not clearly a read is treated as a
    write, because the cost of serialising an extra call is a few milliseconds
    while the cost of racing two writes is a corrupted end-state.
    """
    tail = name.split("_", 1)[-1].lower() if "_" in name else name.lower()
    for verb in _READ_VERBS:
        if tail.startswith(verb):
            return False
    for verb in _WRITE_VERBS:
        if verb in tail:
            return True
    return False


@lru_cache(maxsize=1)
def index() -> dict[str, ToolInfo]:
    from backend.main import get_all_tool_specs

    specs = get_all_tool_specs()
    cluster_of = {t: c.id for c in CLUSTERS for t in c.tools}
    out: dict[str, ToolInfo] = {}
    for name, spec in specs.items():
        out[name] = ToolInfo(
            name=name,
            service=spec.service,
            cluster=cluster_of.get(name, "unclustered"),
            description=spec.description,
            is_write=_classify(name),
        )
    return out


def tool_info(name: str) -> ToolInfo | None:
    return index().get(name)


def is_write(name: str) -> bool:
    info = tool_info(name)
    return True if info is None else info.is_write


def tools_in(cluster_ids: list[str]) -> list[str]:
    """Expand cluster ids to tool names, order-stable and de-duplicated."""
    seen: dict[str, None] = {}
    for cid in cluster_ids:
        cluster = CLUSTERS_BY_ID.get(cid)
        if cluster is None:
            continue
        for name in cluster.tools:
            seen.setdefault(name, None)
    return list(seen)


def describe(name: str) -> str:
    """The description the model sees: one line, plus any behavioural hint."""
    info = tool_info(name)
    base = info.description if info else name
    hint = TOOL_HINTS.get(name)
    return f"{base} {hint}" if hint else base


def cluster_cards() -> list[Cluster]:
    return list(CLUSTERS)
