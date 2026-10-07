"""A runnable live MCP connector for trying the adapter without external accounts.
Start: uv run python scripts/example_mcp.py
Copy docs/connectors.example.json to data/connectors.json, set COS_MCP_CONFIG=data/connectors.json,
and restart Chief Of Staff. These tools use real local notes, not the simulated seven-service catalog.
"""

import sqlite3
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Workspace notes", host="127.0.0.1", port=8765, json_response=True)
DB = Path("data/mcp-notes.sqlite3")


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,content TEXT)")
    return db


@mcp.tool()
def list_notes() -> list[dict]:
    """Read the personal workspace notes."""
    with connect() as db:
        return [{"id": row[0], "content": row[1]} for row in db.execute("SELECT * FROM notes")]


@mcp.tool()
def create_note(content: str) -> dict:
    """Save a workspace note. This changes real local data and requires approval."""
    with connect() as db:
        id = db.execute("INSERT INTO notes(content) VALUES(?)", (content,)).lastrowid
        return {"id": id, "content": content}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
