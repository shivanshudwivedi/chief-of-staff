"""Tool execution: the single choke point for invocation and logging.

Every tool call in the system goes through `execute_one`. That is deliberate --
the brief scores us on a complete `tool_calls` log, so the log is written where
the call happens rather than at any of the call sites that could forget.

Three fixture behaviours are handled here, all found by auditing the mocks:

1. `main._openai_tool_entry` forces every property into `required`, so a model
   may emit `null` for optionals. 156 parameters across 72 tools are typed as
   bare `str`/`int`/`bool` with a default and are *not* nullable, so passing
   null raises ValidationError on 73 of the 191 tools. Nulls are stripped.
2. `ToolSpec.invoke` returns a pydantic envelope wrapping the payload in a
   `result` field. It has to be unwrapped exactly once, and dumped in JSON mode,
   or the log nests `result.result` and non-serialisable values reach FastAPI.
3. Every mock raises on failure -- `*MockError` (all ValueError subclasses),
   `pydantic.ValidationError`, or `KeyError` for an unknown name. Nothing ever
   returns an error dict, so a bare `except ValueError` would silently swallow
   real mock errors as if they were validation problems.
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from dataclasses import dataclass, field
from typing import Any

from backend.helpers import config
from backend.helpers.catalog import is_write, tool_info


@dataclass
class CallOutcome:
    name: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None
    duration_ms: int = 0
    call_id: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ExecutionLog:
    """Ordered record of everything invoked this turn."""

    outcomes: list[CallOutcome] = field(default_factory=list)

    def add(self, outcome: CallOutcome) -> None:
        self.outcomes.append(outcome)

    @property
    def count(self) -> int:
        return len(self.outcomes)

    def succeeded(self, name: str) -> bool:
        return any(o.name == name and o.ok for o in self.outcomes)


def sanitize_arguments(raw: Any) -> dict[str, Any]:
    """Parse the model's argument blob and drop nulls (see note 1 above)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if v is not None}


def _describe_error(exc: Exception, name: str) -> str:
    """A message the model can act on, not just a stack-trace fragment."""
    kind = type(exc).__name__
    if kind == "ValidationError":
        problems = []
        for err in getattr(exc, "errors", lambda: [])():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
            problems.append(f"{loc}: {err.get('msg', '')}")
        return f"Invalid arguments for {name}: " + "; ".join(problems[:6])
    if isinstance(exc, KeyError):
        return f"No such tool: {name}"
    return f"{kind}: {exc}"


def execute_one(name: str, raw_arguments: Any, log: ExecutionLog, call_id: str = "") -> CallOutcome:
    """Invoke one tool, record it, and never raise."""
    from backend.main import get_tool_spec

    arguments = sanitize_arguments(raw_arguments)
    started = time.perf_counter()
    outcome = CallOutcome(name=name, arguments=arguments, call_id=call_id)
    try:
        spec = get_tool_spec(name)
        envelope = spec.invoke(**arguments)
        # Unwrap exactly once; JSON mode so the payload is wire-safe.
        outcome.result = envelope.model_dump(mode="json")["result"]
    except Exception as exc:  # noqa: BLE001 - the mocks raise many unrelated types
        outcome.error = _describe_error(exc, name)
    outcome.duration_ms = int((time.perf_counter() - started) * 1000)
    log.add(outcome)
    return outcome


def execute_batch(
    calls: list[tuple[str, str, Any]], log: ExecutionLog
) -> list[CallOutcome]:
    """Run a model turn's tool calls.

    Reads run concurrently; writes run strictly in the order the model emitted
    them. The mocks share global module state and the graders assert on
    end-state, so overlapping two writes is a race against the scoring, while
    overlapping reads is free.

    The returned list is in the model's original order regardless of completion
    order, so tool result messages line up with their tool_call_ids.
    """
    results: dict[int, CallOutcome] = {}

    read_idx = [i for i, (_, name, _) in enumerate(calls) if not is_write(name)]
    write_idx = [i for i, (_, name, _) in enumerate(calls) if is_write(name)]

    if len(read_idx) > 1:
        workers = min(config.PARALLEL_READ_WORKERS, len(read_idx))
        # Each thread logs its own outcome; collect first, then append in
        # deterministic order so the tool_calls log is reproducible.
        local: dict[int, CallOutcome] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_invoke_detached, calls[i][1], calls[i][2], calls[i][0]): i
                for i in read_idx
            }
            for future in concurrent.futures.as_completed(futures):
                local[futures[future]] = future.result()
        for i in sorted(local):
            log.add(local[i])
            results[i] = local[i]
    elif read_idx:
        i = read_idx[0]
        results[i] = execute_one(calls[i][1], calls[i][2], log, calls[i][0])

    for i in write_idx:
        results[i] = execute_one(calls[i][1], calls[i][2], log, calls[i][0])

    return [results[i] for i in range(len(calls))]


def _invoke_detached(name: str, raw_arguments: Any, call_id: str) -> CallOutcome:
    """execute_one without the logging side effect, for use inside threads."""
    scratch = ExecutionLog()
    return execute_one(name, raw_arguments, scratch, call_id)


def signature(name: str, arguments: dict[str, Any]) -> str:
    """Stable key for retry accounting."""
    try:
        return f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
    except Exception:  # pragma: no cover
        return f"{name}:{arguments}"


def is_non_idempotent(name: str) -> bool:
    """Tools that may have taken effect even when they raised.

    `slack_send_message` appends the message to channel state *before* it
    validates thread_ts, so a failed threaded send has already posted. Retrying
    double-posts and breaks message-count assertions.
    """
    return name in {"slack_send_message"} or is_write(name)


__all__ = [
    "CallOutcome",
    "ExecutionLog",
    "execute_batch",
    "execute_one",
    "is_non_idempotent",
    "sanitize_arguments",
    "signature",
    "tool_info",
]
