"""POST /chat -- the multi-tool orchestrator's entry point.

Kept deliberately thin. Everything of substance lives in `backend/helpers/`:

    router.py    two-stage routing over the 191-tool catalog
    schema.py    compressed, truthfully-typed tool schemas
    executor.py  invocation, argument sanitising, error capture, logging
    policy.py    destructive-tool guards and retry rules
    loop.py      the bounded orchestration loop
    prompts.py   system prompt, including the fixture's frozen clock

The handler stays `def`, not `async def`. `/chat` is registered on a sync route,
so FastAPI runs it in the threadpool; making it async would put a blocking
OpenAI call on the event loop and stall `/health` alongside it.
"""

from __future__ import annotations

from backend.chat_schema import ChatMessage, ChatRequest, ChatResponse, ToolCallLog
from backend.helpers.helpers import outcome_to_log_entry, run_turn


def chat(request: ChatRequest) -> ChatResponse:
    """Answer the conversation, calling whatever tools the task needs.

    Returns the full conversation with the assistant's reply appended, plus an
    ordered log of every tool invoked this turn -- including the ones that
    failed, since a failed call is part of how the answer was reached.
    """
    turn = run_turn(request.messages)

    return ChatResponse(
        messages=[*request.messages, ChatMessage(role="assistant", content=turn.reply)],
        tool_calls=[ToolCallLog(**outcome_to_log_entry(o)) for o in turn.log.outcomes],
    )
