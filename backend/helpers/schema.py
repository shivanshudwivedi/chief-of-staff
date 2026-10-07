"""Tool schemas for the Chat Completions API.

`main.get_openai_tools` emits the flat *Responses API* shape and, for strict
mode, forces every property into `required` -- 929 of them, when only 297 are
genuinely required. Verified against the live API: under strict mode the model
then fills in a value for every optional it was forced to include
(`{"limit":100,"types":"public_channel,...","discover_dms":true}`), whereas the
same tool with a truthful required list is called as `{}`.

So this module re-derives schemas from the pydantic args models:

  1. nest them for Chat Completions,
  2. keep pydantic's own `required` list, which is the truthful one,
  3. drop `default` keywords (redundant once the field is optional),
  4. drop auto-generated parameter descriptions that only restate the parameter
     name, and
  5. use the short one-line description plus a behavioural hint, not the long
     generated docstring.

Steps 3-5 are pure size; step 2 is correctness.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

from backend.helpers.catalog import describe

_BOILERPLATE = (". Required.", ". Optional.")


def _humanised(param: str) -> str:
    """Mirror of tooling._humanize_parameter_name, for detecting no-op docs."""
    acronyms = {
        "id": "ID", "ids": "IDs", "url": "URL", "uri": "URI", "html": "HTML",
        "cc": "CC", "bcc": "BCC", "api": "API", "uid": "UID", "ical": "iCal",
        "uuid": "UUID", "rsvp": "RSVP",
    }
    words = []
    for chunk in param.replace("-", "_").split("_"):
        if chunk:
            words.append(acronyms.get(chunk.lower(), chunk.capitalize()))
    return " ".join(words) or param


def _is_noop_description(param: str, description: str) -> bool:
    text = description
    for suffix in _BOILERPLATE:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    else:
        marker = ". Optional; defaults to "
        if marker in text:
            text = text.split(marker)[0]
    return text.strip() == _humanised(param)


def _prune(node: Any, param: str | None = None) -> Any:
    """Strip `default`, `title` and no-information descriptions, recursively."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in ("default", "title"):
                continue
            if key == "description" and param and isinstance(value, str):
                if _is_noop_description(param, value):
                    continue
                for suffix in _BOILERPLATE:
                    if value.endswith(suffix):
                        value = value[: -len(suffix)]
                        break
                else:
                    marker = ". Optional; defaults to "
                    if marker in value:
                        value = value.split(marker)[0]
            if key == "properties" and isinstance(value, dict):
                out[key] = {k: _prune(v, k) for k, v in value.items()}
                continue
            out[key] = _prune(value, param)
        return out
    if isinstance(node, list):
        return [_prune(v, param) for v in node]
    return node


@lru_cache(maxsize=256)
def tool_schema(name: str) -> dict[str, Any]:
    from backend.main import get_tool_spec

    spec = get_tool_spec(name)
    parameters = _prune(copy.deepcopy(spec.args_model.model_json_schema()))
    parameters.setdefault("type", "object")
    parameters.setdefault("properties", {})
    # pydantic's own required list -- the truthful one, unlike main.py's forced version.
    parameters.setdefault("required", [])
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": describe(name),
            "parameters": parameters,
        },
    }


def tools_payload(names: list[str]) -> list[dict[str, Any]]:
    return [tool_schema(n) for n in names]
