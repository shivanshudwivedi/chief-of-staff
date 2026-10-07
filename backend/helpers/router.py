"""Two-stage tool routing over the 191-tool catalog.

The whole catalog is 288k characters of JSON schema (~72k tokens) per model
call, which is both unaffordable and, well past a hundred functions, actively
worse for selection accuracy. Routing narrows that to one or two clusters --
typically 3-8k characters.

Stage 0  lexical scorer      0 tokens, sub-millisecond, deterministic
Stage 1  cluster-select LLM  ~2k tokens, one cheap call, only when needed

The gate between them is the latency win: when Stage 0 is confident (one
cluster well clear of the runner-up), Stage 1 is skipped entirely and the turn
costs one model call instead of two. "What conversations do I have in Slack?"
never reaches the router LLM.

The merge is deliberately recall-biased. A missing cluster fails the scenario;
a spare one costs about 1.3k tokens.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from backend.helpers import config
from backend.helpers.catalog import cluster_cards, tools_in
from backend.helpers.clusters import CLUSTERS_BY_ID

_WORD = re.compile(r"[a-z0-9_.\-#]+")

# A cluster at or above this score counts as evidence that its service is involved.
_SERVICE_FLOOR = 1.5


@dataclass
class RouteDecision:
    clusters: list[str]
    tools: list[str]
    stage: str  # "lexical-gate" | "llm" | "fallback"
    lexical_scores: dict[str, float] = field(default_factory=dict)
    llm_clusters: list[str] = field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def lexical_scores(text: str) -> dict[str, float]:
    """Score clusters by keyword and tool-name overlap with the user's words."""
    lowered = text.lower()
    words = _tokens(text)
    scores: dict[str, float] = {}
    for cluster in cluster_cards():
        score = 0.0
        for keyword in cluster.keywords:
            if " " in keyword or "." in keyword or "-" in keyword:
                # Multi-word and punctuated keys ("pull request", ".xlsx") are
                # strong signals and are matched as substrings.
                if keyword in lowered:
                    score += 2.5
            elif keyword in words:
                score += 1.5
        # A literal tool name in the prompt is close to decisive.
        for tool in cluster.tools:
            if tool.lower() in lowered:
                score += 4.0
        if cluster.service in words:
            score += 2.0
        if score:
            scores[cluster.id] = round(score, 2)
    return dict(sorted(scores.items(), key=lambda kv: -kv[1]))


def _gate(scores: dict[str, float]) -> list[str] | None:
    """Return clusters when Stage 0 is confident enough to skip Stage 1.

    Two rules, both earned from measurement rather than intuition:

    1. Fire only when the request is plausibly *single-service*. An early
       version keyed on score and margin alone, and it happily gated "find the
       email about X and post it to Slack" to Slack -- the Gmail half was
       silently unroutable. Counting distinct services is what makes skipping
       the router call safe at all.
    2. When it does fire, take the whole service (tool-count permitting), not
       just the clusters that scored. The sweep in _work/routing_eval.py showed
       every remaining bad gate was a sibling-cluster miss inside the correct
       service -- "Add a comment to ENG-4" reaching linear_issues but not
       linear_comments.
    """
    if not scores:
        return None
    scoring = {
        cid: sc for cid, sc in scores.items()
        if cid in CLUSTERS_BY_ID and sc >= _SERVICE_FLOOR
    }
    if len({CLUSTERS_BY_ID[cid].service for cid in scoring}) != 1:
        return None

    top_id, top = next(iter(scores.items()))
    if top < config.LEXICAL_GATE_MIN_SCORE:
        return None

    service = CLUSTERS_BY_ID[top_id].service
    whole = [c.id for c in cluster_cards() if c.service == service]
    if len(tools_in(whole)) <= config.GATE_WHOLE_SERVICE_MAX_TOOLS:
        return whole
    return [cid for cid in scoring if CLUSTERS_BY_ID[cid].service == service]


def _router_prompt() -> str:
    lines = [
        "You route a user request to the tool groups needed to fulfil it.",
        "",
        "Groups:",
    ]
    for cluster in cluster_cards():
        sample = ", ".join(cluster.tools[:4])
        lines.append(f"- {cluster.id} [{cluster.service}]: {cluster.summary} (e.g. {sample})")
    lines += [
        "",
        "Return JSON: {\"clusters\": [\"id\", ...]}",
        f"Choose every group the request needs, at most {config.MAX_ROUTED_CLUSTERS}.",
        "A request spanning two services needs a group from each.",
        "Prefer including a borderline group over omitting it: a missing group makes the",
        "task impossible, while a spare one is nearly free.",
        "If the request needs no tools at all (a greeting, or a question about the",
        "conversation itself), return an empty list.",
    ]
    return "\n".join(lines)


def _ask_router(client, user_text: str) -> list[str]:
    valid = {c.id for c in cluster_cards()}
    try:
        response = client.chat.completions.create(
            model=config.ROUTER_MODEL,
            messages=[
                {"role": "system", "content": _router_prompt()},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
            timeout=config.REQUEST_TIMEOUT_S,
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        picked = payload.get("clusters") or []
        return [c for c in picked if c in valid][: config.MAX_ROUTED_CLUSTERS]
    except Exception:
        return []


def route(client, user_text: str, *, extra_clusters: list[str] | None = None) -> RouteDecision:
    scores = lexical_scores(user_text)
    forced = list(extra_clusters or [])

    gated = _gate(scores) if not forced else None
    if gated:
        clusters = gated
        stage = "lexical-gate"
        llm_picked: list[str] = []
    else:
        llm_picked = _ask_router(client, user_text)
        # Union with confident lexical hits: the scorer catches fixture nouns
        # ("budget_2025.xlsx", "ENG-4") that a summary-level router can miss.
        clusters = list(dict.fromkeys(forced + llm_picked))
        for cid, score in scores.items():
            if len(clusters) >= config.MAX_ROUTED_CLUSTERS:
                break
            if score >= config.LEXICAL_GATE_MIN_SCORE and cid not in clusters:
                clusters.append(cid)
        stage = "llm" if llm_picked else ("fallback" if clusters else "none")

    tools = tools_in(clusters)[: config.MAX_ROUTED_TOOLS]
    return RouteDecision(
        clusters=clusters,
        tools=tools,
        stage=stage,
        lexical_scores=dict(list(scores.items())[:6]),
        llm_clusters=llm_picked,
    )
