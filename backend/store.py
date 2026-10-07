"""SQLite journal. Each operation uses its own connection; writes are transactional."""

from __future__ import annotations
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from backend.redaction import redact


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, path=None):
        self.path = str(path or os.getenv("COS_DB_PATH", "data/chief.sqlite3"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT,channel TEXT,
              recipient TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT,role TEXT,
              content TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,conversation_id TEXT,status TEXT,
              mode TEXT,started_at TEXT,finished_at TEXT,trace TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,run_id TEXT,name TEXT,arguments TEXT,
              result TEXT,error TEXT,duration_ms INTEGER,created_at TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT,status TEXT,priority TEXT,
              due TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,content TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,run_id TEXT,name TEXT,arguments TEXT,
              status TEXT,result TEXT,error TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS inbox(external_id TEXT PRIMARY KEY,sender TEXT,content TEXT,
              conversation_id TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,recipient TEXT,content TEXT,status TEXT,
              created_at TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def query(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount

    def conversation(self, title="New conversation", channel="web", recipient=None):
        id = uid()
        self.execute(
            "INSERT INTO conversations VALUES(?,?,?,?,?)",
            (id, redact(title[:100], pii=False), channel, recipient, now()),
        )
        return id

    def message(self, cid, role, content):
        self.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?)", (uid(), cid, role, redact(content, pii=False), now())
        )

    def messages(self, cid):
        return self.query("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (cid,))

    def event(self, rid, name, args, result=None, error=None, duration=0):
        self.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            (
                uid(),
                rid,
                name,
                json.dumps(redact(args)),
                json.dumps(redact(result), default=str),
                redact(error),
                duration,
                now(),
            ),
        )

    def approval(self, rid, name, args):
        encoded = json.dumps(args, sort_keys=True)
        with self.connect() as db:
            found = db.execute(
                "SELECT id FROM approvals WHERE run_id=? AND name=? AND arguments=?", (rid, name, encoded)
            ).fetchone()
            if found:
                return found["id"]
            id = uid()
            db.execute(
                "INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)",
                (id, rid, name, encoded, "pending", None, None, now()),
            )
            return id

    def seed(self):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
                return
            db.execute("INSERT INTO settings VALUES('seeded','true')")
            for title, priority in [
                ("Prepare the launch decision memo", "high"),
                ("Review the revenue follow-up", "high"),
                ("Protect a block of focus time", "normal"),
            ]:
                db.execute(
                    "INSERT INTO tasks VALUES(?,?,?,?,?,?)", (uid(), title, "open", priority, None, now())
                )
            db.execute(
                "INSERT INTO memories VALUES(?,?,?)",
                (uid(), "Demo preference: keep briefings concise and protect morning focus time.", now()),
            )

    def snapshot(self):
        data = {
            table: self.query(f"SELECT * FROM {table} ORDER BY created_at DESC")
            for table in ("conversations", "tasks", "memories", "approvals", "outbox")
        }
        data["tasks"] = self.query(
            "SELECT * FROM tasks ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, created_at DESC"
        )
        data["runs"] = self.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT 50")
        data["events"] = self.query("SELECT * FROM events ORDER BY created_at DESC LIMIT 150")
        for row in data["approvals"] + data["events"]:
            for key in ("arguments", "result"):
                if row.get(key):
                    row[key] = json.loads(row[key])
        for row in data["runs"]:
            row["trace"] = json.loads(row["trace"] or "{}")
        return data
