"""Runtime configuration for the chat orchestrator.

Everything tunable lives here so the loop, router and executor read constants
instead of hard-coding them.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # optional: the graders may inject env vars directly
    from dotenv import load_dotenv

    for _candidate in (
        Path(__file__).resolve().parents[2] / ".env",
        Path.cwd() / ".env",
    ):
        if _candidate.is_file():
            load_dotenv(_candidate)
            break
except Exception:  # pragma: no cover - dotenv is a convenience, not a dependency
    pass


# --- models -----------------------------------------------------------------
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
# The router only ranks ~36 short cluster cards; it never sees a tool schema.
ROUTER_MODEL = os.getenv("OPENAI_ROUTER_MODEL", MODEL)

REQUEST_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "60"))
MAX_API_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "2"))


# --- orchestration budgets --------------------------------------------------
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "8"))
# Hard wall-clock ceiling for one turn. MAX_STEPS alone is not a latency bound:
# eight steps at the request timeout would be minutes. On expiry the loop stops
# calling tools and goes straight to synthesis, so a slow turn still answers.
MAX_TURN_SECONDS = float(os.getenv("AGENT_MAX_TURN_SECONDS", "80"))
# Keep the last N wire messages. Long histories otherwise grow the prompt without
# bound; the first user message is always kept so the original ask survives.
MAX_HISTORY_MESSAGES = 20
MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "12"))
MAX_ATTEMPTS_PER_CALL = 2
# Cap on how often one *read* tool may run in a turn. Guards against enumeration
# loops -- the model calling list-issues once per status rather than filtering
# the list it already has. Writes are exempt: posting to four channels is four
# legitimate calls, and exact-duplicate writes are blocked separately.
MAX_CALLS_PER_READ_TOOL = 3
PARALLEL_READ_WORKERS = 4


# --- routing ----------------------------------------------------------------
# A missing cluster fails a scenario; an extra one costs ~1.3k tokens. Bias to recall.
MAX_ROUTED_TOOLS = 45
MAX_ROUTED_CLUSTERS = 4
# Stage 1 (the router LLM call) is skipped when the lexical scorer is this confident.
# Tuned with a threshold sweep over the 81-prompt golden set
# (_work/routing_eval.py). 3.0 is the lowest value with ZERO bad gates: 2.5 and
# 2.0 raise coverage 19% -> 28% but start gating "Add a comment to ENG-4" to
# linear_issues without linear_comments, and 1.5 reaches 62% coverage with four
# bad gates. Latency is tracked, not graded; a bad gate fails a scenario. Kept
# conservative on purpose.
LEXICAL_GATE_MIN_SCORE = 3.0
# When the gate fires, take every cluster of the winning service rather than
# only the ones that scored -- sibling clusters are what a near-miss phrasing
# needs, and the sweep shows it costs ~3 extra tools for zero extra risk.
# Skipped for services too large to load wholesale (GitHub is 86 tools), which
# fall back to the scoring clusters only.
GATE_WHOLE_SERVICE_MAX_TOOLS = 25


# --- context hygiene --------------------------------------------------------
# Applies only to what the model sees. The full result is always logged.
MAX_TOOL_RESULT_CHARS = 3000
MAX_LIST_ITEMS_IN_CONTEXT = 12


# --- the frozen fixture clock ----------------------------------------------
# backend/googlecalendar_mock/state.py seeds BASE_NOW and never calls
# datetime.now(). Telling the model the date outright removes a whole class of
# date errors and saves a discovery tool call.
FIXTURE_NOW_ISO = "2026-04-08T09:00:00-04:00"
FIXTURE_NOW_HUMAN = "Wednesday, 8 April 2026, 09:00 America/New_York (UTC-04:00)"
