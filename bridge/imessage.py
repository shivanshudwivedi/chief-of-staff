#!/usr/bin/env python3
"""Opt-in macOS Messages bridge. Read-only DB polling; explicit approved outbound sends."""

from __future__ import annotations
import argparse
import json
import os
import platform
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Use argv rather than interpolate message content into AppleScript or a shell.
APPLE_SCRIPT = """on run argv
    tell application "Messages"
        set targetService to first service whose service type = iMessage
        set targetBuddy to buddy (item 1 of argv) of targetService
        send (item 2 of argv) to targetBuddy
    end tell
end run"""


def send(recipient, content):
    subprocess.run(
        ["osascript", "-e", APPLE_SCRIPT, recipient, content],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def read_messages(db_path, after, allowlist):
    # Connect mode=ro rather than copying personal Messages history.
    with sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        scanned = db.execute(
            "SELECT ROWID FROM message WHERE ROWID>? ORDER BY ROWID LIMIT 200", (after,)
        ).fetchall()
        watermark = scanned[-1][0] if scanned else after
        # Ignore group chats, outgoing messages, attachments and SMS. Never ingest non-command texts.
        rows = db.execute(
            """SELECT m.ROWID AS rowid,m.guid,m.text,h.id AS sender
          FROM message m JOIN handle h ON m.handle_id=h.ROWID
          JOIN chat_message_join cm ON cm.message_id=m.ROWID
          WHERE m.ROWID>? AND m.ROWID<=? AND m.is_from_me=0 AND m.service='iMessage'
          AND (SELECT COUNT(*) FROM chat_handle_join ch WHERE ch.chat_id=cm.chat_id)=1
          ORDER BY m.ROWID LIMIT 200""",
            (after, watermark),
        ).fetchall()
        result = [
            dict(r)
            for r in rows
            if r["sender"] in allowlist and r["text"] and r["text"].lower().startswith("/cos ")
        ]
        # Advance over every inspected row, but only after server acceptance.
        return result, watermark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate configuration and DB access without importing or sending",
    )
    parser.add_argument("--db", default=str(Path.home() / "Library/Messages/chat.db"))
    args = parser.parse_args()
    if platform.system() != "Darwin":
        raise SystemExit("The native iMessage bridge requires macOS.")
    token = os.getenv("COS_BRIDGE_TOKEN", "")
    allowed = {s.strip() for s in os.getenv("COS_IMESSAGE_ALLOWLIST", "").split(",") if s.strip()}
    url = os.getenv("COS_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Bridge URL must use HTTP loopback; remote transfer is unsupported.")
    if os.getenv("COS_IMESSAGE_ENABLED", "false").lower() != "true" or len(token) < 24 or not allowed:
        raise SystemExit(
            "Set COS_IMESSAGE_ENABLED=true, a 24+ character bridge token, and a recipient allowlist in .env"
        )
    try:
        with sqlite3.connect(Path(args.db).resolve().as_uri() + "?mode=ro", uri=True) as db:
            newest = db.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0]
    except sqlite3.Error:
        raise SystemExit(
            "Cannot read Messages database. Grant Full Disk Access to the terminal running this bridge."
        )
    if args.check:
        print(
            "Configuration and read-only DB access verified. No history imported; no messages sent. Automation permission will be checked on first approved send."
        )
        return
    checkpoint = ROOT / "data/imessage-cursor.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    cursor = json.loads(checkpoint.read_text())["rowid"] if checkpoint.exists() else newest
    with httpx.Client(base_url=url, headers={"Authorization": "Bearer " + token}, timeout=30) as client:
        while True:
            try:
                client.post("/bridge/heartbeat", json={"status": "connected"}).raise_for_status()
                messages, watermark = read_messages(args.db, cursor, allowed)
                for message in messages:
                    client.post(
                        "/bridge/inbound",
                        json={
                            "external_id": message["guid"] or str(message["rowid"]),
                            "sender": message["sender"],
                            "content": message["text"],
                        },
                    ).raise_for_status()
                # Atomic checkpoint; an HTTP failure leaves cursor unchanged for deduplicated replay.
                tmp = checkpoint.with_suffix(".tmp")
                tmp.write_text(json.dumps({"rowid": watermark}))
                tmp.replace(checkpoint)
                cursor = watermark
                claim = client.post("/bridge/outbox/claim")
                claim.raise_for_status()
                outgoing = claim.json()["message"]
                if outgoing:
                    status, error = "accepted", None
                    try:
                        if outgoing["recipient"] not in allowed:
                            raise ValueError("Recipient is not locally allowlisted")
                        send(outgoing["recipient"], outgoing["content"])
                    except Exception as exc:
                        # A timeout/error can occur after Messages accepted the send. Never automatically retry.
                        status, error = (
                            "uncertain",
                            type(exc).__name__ + ": inspect Messages before retrying manually",
                        )
                    client.post(
                        f"/bridge/outbox/{outgoing['id']}/ack", json={"status": status, "error": error}
                    ).raise_for_status()
            except (httpx.HTTPError, sqlite3.Error) as exc:
                print("Bridge temporarily unavailable:", type(exc).__name__, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
