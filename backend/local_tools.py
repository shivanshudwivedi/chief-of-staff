"""Typed first-party tools shared by the demo and model-backed executor."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.store import now, uid


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Empty(Arguments):
    pass


class AddTask(Arguments):
    title: str = Field(min_length=1, max_length=300)
    priority: Literal["high", "normal", "low"] = "normal"
    due: str | None = Field(default=None, description="Optional ISO date/time; do not invent a deadline")


class CompleteTask(Arguments):
    task_id: str


class Remember(Arguments):
    content: str = Field(min_length=1, max_length=2000)


class SearchMemory(Arguments):
    query: str = ""


class DraftMessage(Arguments):
    recipient: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)


TOOLS = {
    "tasks_list": (Empty, "Read the user's persistent tasks and priorities."),
    "tasks_add": (AddTask, "Create a personal task. Local reversible action; no approval required."),
    "tasks_complete": (CompleteTask, "Complete a task by its exact ID; look it up first."),
    "memory_remember": (Remember, "Save a preference only when the user explicitly asks you to remember it."),
    "memory_search": (SearchMemory, "Search explicitly saved user preferences and context."),
    "imessage_read": (Empty, "Read commands imported by the opt-in allowlisted iMessage bridge."),
    "imessage_draft": (
        DraftMessage,
        "Propose an outgoing iMessage to an allowlisted recipient. Requires approval.",
    ),
}


def schemas():
    return [
        {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": cls.model_json_schema()},
        }
        for name, (cls, desc) in TOOLS.items()
    ]


def invoke(store, name, args):
    args = TOOLS[name][0].model_validate(args).model_dump()
    if name == "tasks_list":
        return {
            "tasks": store.query(
                "SELECT * FROM tasks ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, created_at DESC"
            )
        }
    if name == "tasks_add":
        id = uid()
        store.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?)",
            (id, args["title"], "open", args["priority"], args["due"], now()),
        )
        return {"id": id, **args, "status": "open"}
    if name == "tasks_complete":
        changed = store.execute("UPDATE tasks SET status='done' WHERE id=?", (args["task_id"],))
        if not changed:
            raise ValueError("Task does not exist")
        return {"id": args["task_id"], "status": "done"}
    if name == "memory_remember":
        id = uid()
        store.execute("INSERT INTO memories VALUES(?,?,?)", (id, args["content"], now()))
        return {"id": id, "content": args["content"]}
    if name == "memory_search":
        rows = store.query("SELECT * FROM memories ORDER BY created_at DESC")
        return {"memories": [r for r in rows if args["query"].lower() in r["content"].lower()]}
    if name == "imessage_read":
        return {"messages": store.query("SELECT * FROM inbox ORDER BY created_at DESC LIMIT 30")}
    raise ValueError("Outgoing messages must go through the approval queue")
