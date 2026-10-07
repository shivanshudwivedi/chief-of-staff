"""`find_tools` -- the mid-turn escape hatch out of a routing mistake.

Routing happens once, before the loop starts, from the user's opening words. Two
things can go wrong with that bet:

  1. the router simply misses (unusual phrasing, a service named only obliquely);
  2. step three of a plan needs a service nobody could have predicted from step one.

Without a way out, both end the same way -- the model has no tool for the job and
is left to either give up or invent an answer. Inventing is the worse failure and
exactly what the brief penalises.

So one synthetic tool is always in scope. Calling it re-runs the lexical scorer
over a free-text description of what is needed and *adds* the matching clusters
to the live tool set for the rest of the turn.

It is not a registry tool, so it is deliberately absent from `tool_calls`: that
log is a record of the 191 mocked tools that were invoked, and padding it with
our own bookkeeping would misreport the tool count being scored. The trace
records every use instead.
"""

from __future__ import annotations

from typing import Any

from backend.helpers.catalog import describe, tools_in
from backend.helpers.clusters import CLUSTERS_BY_ID

FIND_TOOLS = "find_tools"

SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": FIND_TOOLS,
        "description": (
            "Search the full catalog of 191 tools when the tools currently available to you "
            "do not cover what the user asked for. Describe the capability you need in plain "
            "words (e.g. 'post a message to a Slack channel', 'find a file in Google Drive'). "
            "The matching tools are added to your available tools, so call this BEFORE telling "
            "the user something cannot be done."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "need": {
                    "type": "string",
                    "description": "The capability needed, in plain words.",
                }
            },
            "required": ["need"],
        },
    },
}


def find(need: str, already: set[str], limit: int = 3) -> tuple[list[str], str]:
    """Return (newly available tool names, a message for the model)."""
    from backend.helpers.router import lexical_scores

    scores = lexical_scores(need or "")
    picked = [cid for cid, _ in list(scores.items())[:limit]]

    if not picked:
        return [], (
            "No tools matched that description. The catalog covers Gmail, Google Calendar, "
            "Google Drive, Slack, Linear, GitHub and Perplexity. Either rephrase the "
            "capability, or tell the user plainly that it is not supported."
        )

    names = [n for n in tools_in(picked) if n not in already]
    if not names:
        return [], (
            "Those tools are already available to you. Use the ones you have, or tell the "
            "user what cannot be done."
        )

    listing = "\n".join(f"- {n}: {describe(n)}" for n in names[:25])
    groups = ", ".join(CLUSTERS_BY_ID[c].id for c in picked if c in CLUSTERS_BY_ID)
    return names, f"Added tools from {groups}. You can now call:\n{listing}"
