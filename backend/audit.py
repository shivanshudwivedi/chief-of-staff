"""Append-only, hash-chained security journal with redaction before persistence."""

from __future__ import annotations
import hashlib
import json
from backend.redaction import redact
from backend.store import now, uid

GENESIS = "0" * 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class Audit:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS audit_records(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE,created_at TEXT,actor TEXT,action TEXT,resource TEXT,outcome TEXT,payload TEXT,
            previous_hash TEXT,record_hash TEXT);
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_records
              BEGIN SELECT RAISE(ABORT,'Audit records are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_records
              BEGIN SELECT RAISE(ABORT,'Audit records are append-only'); END;""")

    def append(self, actor, action, resource, outcome, payload=None):
        fields = redact(
            {
                "id": uid(),
                "created_at": now(),
                "actor": actor,
                "action": action,
                "resource": resource,
                "outcome": outcome,
                "payload": payload or {},
            }
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute("SELECT record_hash FROM audit_records ORDER BY seq DESC LIMIT 1").fetchone()
            previous = last["record_hash"] if last else GENESIS
            digest = hashlib.sha256((previous + canonical(fields)).encode()).hexdigest()
            db.execute(
                "INSERT INTO audit_records(id,created_at,actor,action,resource,outcome,payload,previous_hash,record_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    fields["id"],
                    fields["created_at"],
                    fields["actor"],
                    fields["action"],
                    fields["resource"],
                    fields["outcome"],
                    canonical(fields["payload"]),
                    previous,
                    digest,
                ),
            )
        return digest

    def records(self, limit=200):
        rows = self.store.query("SELECT * FROM audit_records ORDER BY seq DESC LIMIT ?", (limit,))
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def verify(self):
        rows = self.store.query("SELECT * FROM audit_records ORDER BY seq")
        previous = GENESIS
        for row in rows:
            fields = {k: row[k] for k in ("id", "created_at", "actor", "action", "resource", "outcome")}
            fields["payload"] = json.loads(row["payload"])
            expected = hashlib.sha256((previous + canonical(fields)).encode()).hexdigest()
            if row["previous_hash"] != previous or row["record_hash"] != expected:
                return {"valid": False, "checked": len(rows), "failed_sequence": row["seq"]}
            previous = row["record_hash"]
        return {
            "valid": True,
            "checked": len(rows),
            "head": previous,
            "boundary": "Local integrity check; an external retained head is needed to detect full-chain rewrites/truncation",
        }
