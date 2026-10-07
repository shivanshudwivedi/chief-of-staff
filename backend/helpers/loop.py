"""The orchestration loop.

A bounded ReAct loop with no separate planner: for tasks this size a planning
call mostly adds latency and a second place for the plan to be wrong, and the
routing stage already supplies the structure a planner would have given.

Four ways a turn ends, none of them "ran out of road":
  1. the model replies with no tool calls -- that is the answer;
  2. a budget is exhausted (steps, tool calls, or wall clock) -- a final
     synthesis call runs with tools disabled, so the user always gets a real
     answer describing what did and did not happen;
  3. the model asks a clarifying question and calls nothing;
  4. an unrecoverable error -- reported plainly, never dressed up as success.

Routing is a bet placed before the loop starts. `find_tools` is the way to
recover from a bad bet mid-turn without abandoning the task.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from backend.helpers import config, observability, toolfinder
from backend.helpers.compaction import to_tool_message
from backend.helpers.executor import (
    CallOutcome,
    ExecutionLog,
    execute_batch,
    sanitize_arguments,
    signature,
)
from backend.helpers.policy import Policy
from backend.helpers.prompts import SYNTHESIS, system_message
from backend.helpers.router import route
from backend.helpers.schema import tools_payload

_FALLBACK = (
    "I could not complete that because the language model was unreachable. "
    "No changes were made. Please try again."
)


@dataclass
class TurnResult:
    reply: str
    log: ExecutionLog
    trace: dict[str, Any] = field(default_factory=dict)


def _client() -> OpenAI:
    return OpenAI(timeout=config.REQUEST_TIMEOUT_S, max_retries=config.MAX_API_RETRIES)


def _to_openai_messages(messages: list[Any]) -> list[dict[str, str]]:
    """Map the wire conversation onto OpenAI messages.

    ChatMessage.content is a plain string and the role set is fixed, so tool
    context from earlier turns does not survive -- only text does. That is why
    the final answer has to carry its findings in prose rather than gesture at
    them.

    A caller-supplied system message is preserved as context rather than
    dropped; ours still leads, so environment facts cannot be overridden by
    accident, but a genuine instruction in the request is not silently lost.
    """
    out: list[dict[str, str]] = []
    for message in messages:
        role = message.role
        content = message.content
        if role == "system":
            out.append({"role": "system", "content": f"Additional instruction from the caller: {content}"})
        elif role == "tool":
            out.append({"role": "assistant", "content": f"(earlier tool result) {content}"})
        else:
            out.append({"role": role, "content": content})

    if len(out) > config.MAX_HISTORY_MESSAGES:
        # Keep the opening turn -- it usually carries the actual goal -- plus the
        # most recent exchanges.
        out = out[:1] + out[-(config.MAX_HISTORY_MESSAGES - 1) :]
    return out


def _last_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content if messages else ""


def _assistant_turn(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return payload


def _complete(client: OpenAI, convo: list[dict[str, Any]], tools: list[dict] | None) -> Any:
    """One model call, tolerant of providers that reject parallel_tool_calls."""
    kwargs: dict[str, Any] = {"model": config.MODEL, "messages": convo}
    if tools:
        kwargs["tools"] = tools
        kwargs["parallel_tool_calls"] = True
    try:
        return client.chat.completions.create(**kwargs)
    except Exception:
        if "parallel_tool_calls" not in kwargs:
            raise
        kwargs.pop("parallel_tool_calls")
        return client.chat.completions.create(**kwargs)


def run_turn(messages: list[Any]) -> TurnResult:
    started = time.perf_counter()
    log = ExecutionLog()
    user_text = _last_user_text(messages)
    trace: dict[str, Any] = {"user": user_text[:160], "steps": []}

    def elapsed() -> float:
        return time.perf_counter() - started

    try:
        client = _client()
    except Exception as exc:  # missing key, bad config
        trace["fatal"] = str(exc)[:200]
        observability.emit(trace)
        return TurnResult(_FALLBACK, log, trace)

    decision = route(client, user_text)
    trace["route"] = {
        "stage": decision.stage,
        "clusters": decision.clusters,
        "tool_count": len(decision.tools),
        "lexical": decision.lexical_scores,
    }

    active: list[str] = list(decision.tools)
    # find_tools is always in scope, including when routing selected nothing, so
    # a routing miss is recoverable instead of terminal.
    tools = tools_payload(active) + [toolfinder.SCHEMA]

    policy = Policy(user_text=user_text)
    convo: list[dict[str, Any]] = [system_message(), *_to_openai_messages(messages)]
    reply = ""
    stopped = None

    for step in range(config.MAX_STEPS):
        if elapsed() > config.MAX_TURN_SECONDS:
            stopped = "time-budget"
            break

        step_started = time.perf_counter()
        try:
            response = _complete(client, convo, tools)
        except Exception as exc:
            trace["steps"].append({"step": step, "error": str(exc)[:200]})
            stopped = "api-error"
            break

        message = response.choices[0].message
        requested = message.tool_calls or []
        trace["steps"].append(
            {
                "step": step,
                "ms": int((time.perf_counter() - step_started) * 1000),
                "tools": [c.function.name for c in requested],
            }
        )

        if not requested:
            reply = (message.content or "").strip()
            break

        convo.append(_assistant_turn(message))

        runnable: list[tuple[str, str, Any]] = []
        batch_seen: set[str] = set()
        expanded = False

        for call in requested:
            name = call.function.name
            arguments = sanitize_arguments(call.function.arguments)

            # The escape hatch: handled here, never sent to the registry, and
            # never written to tool_calls (it is not one of the 191 tools).
            if name == toolfinder.FIND_TOOLS:
                added, note = toolfinder.find(arguments.get("need", ""), set(active))
                if added:
                    active.extend(added)
                    tools = tools_payload(active) + [toolfinder.SCHEMA]
                    expanded = True
                trace.setdefault("find_tools", []).append(
                    {"need": arguments.get("need", "")[:80], "added": len(added)}
                )
                convo.append({"role": "tool", "tool_call_id": call.id, "content": note})
                continue

            key = signature(name, arguments)
            if key in batch_seen:
                convo.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": f"Refused: duplicate of another {name} call in this same batch.",
                })
                continue

            refusal = policy.check(name, arguments)
            if refusal:
                convo.append({"role": "tool", "tool_call_id": call.id, "content": refusal})
            else:
                batch_seen.add(key)
                runnable.append((call.id, name, call.function.arguments))

        if runnable:
            outcomes = execute_batch(runnable, log)
            for (call_id, name, _), outcome in zip(runnable, outcomes):
                if outcome.error:
                    policy.record_failure(name, outcome.arguments)
                else:
                    policy.record_success(name, outcome.arguments)
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": to_tool_message(outcome.result, outcome.error),
                    }
                )

        if log.count >= config.MAX_TOOL_CALLS:
            stopped = "tool-budget"
            break
        if expanded:
            continue
    else:
        stopped = "step-budget"

    if stopped:
        trace["stopped"] = stopped

    if not reply:
        reply = _synthesise(client, convo, trace)

    trace["tool_calls"] = log.count
    trace["total_ms"] = int(elapsed() * 1000)
    observability.emit(trace)
    return TurnResult(reply, log, trace)


def _synthesise(client: OpenAI, convo: list[dict[str, Any]], trace: dict) -> str:
    """Final answer with tools disabled, so a budget stop still answers the user."""
    try:
        response = client.chat.completions.create(
            model=config.MODEL,
            messages=[*convo, {"role": "user", "content": SYNTHESIS}],
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        trace["synthesis_error"] = str(exc)[:200]
        text = ""
    return text or _FALLBACK


def outcome_to_log_entry(outcome: CallOutcome) -> dict[str, Any]:
    return {
        "name": outcome.name,
        "arguments": outcome.arguments,
        "result": outcome.result,
        "error": outcome.error,
    }
