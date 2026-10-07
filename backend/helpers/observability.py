"""One structured trace line per turn.

Emitted through `logging`, not the response body: `ChatResponse` strips unknown
fields, so anything extra returned on the wire is silently dropped anyway.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("chat.turn")


def emit(trace: dict) -> None:
    try:
        logger.info(json.dumps(trace, default=str))
    except Exception:  # pragma: no cover - telemetry must never break a turn
        pass
