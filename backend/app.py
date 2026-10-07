"""Product API: durable background jobs, local-only browser surface, and authenticated bridge."""

from __future__ import annotations
import asyncio
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from backend.engine import Engine, EXECUTION_LOCK, allowed_recipients, bridge_enabled
from backend.store import Store, now, uid
from backend.security import CURRENT, effective, required, route_capability, ROLE_CAPABILITIES
from backend.redaction import redact

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=16000)
    conversation_id: str | None = None


class Decision(BaseModel):
    approve: bool


class Inbound(BaseModel):
    self_command: bool = False
    external_id: str = Field(min_length=1, max_length=200)
    sender: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=16000)


class Ack(BaseModel):
    status: str
    error: str | None = Field(default=None, max_length=1000)


class Heartbeat(BaseModel):
    status: str = "connected"


def create_app(path=None):
    store = Store(path)
    engine = Engine(store)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chief")
    store.execute(
        "CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,conversation_id TEXT,content TEXT,"
        "status TEXT,result TEXT,created_at TEXT)"
    )

    store.execute("CREATE TABLE IF NOT EXISTS job_principals(job_id TEXT PRIMARY KEY,principal_id TEXT)")

    def work(jid):
        changed = store.execute("UPDATE jobs SET status='running' WHERE id=? AND status='queued'", (jid,))
        if not changed:
            return
        job = store.query("SELECT * FROM jobs WHERE id=?", (jid,))[0]
        try:
            identity = store.query("SELECT principal_id FROM job_principals WHERE job_id=?", (jid,))
            principal = engine.auth.resolve(identity[0]["principal_id"] if identity else "local-owner")
            result = engine.run(job["conversation_id"], job["content"], principal)
            status = "failed" if result["status"] == "failed" else "completed"
        except Exception:
            result, status = {"error": "Run interrupted. Check the activity log."}, "failed"
        store.execute("UPDATE jobs SET status=?,result=? WHERE id=?", (status, json.dumps(result), jid))

    def enqueue(cid, content):
        jid = uid()
        store.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?,?)",
            (jid, cid, redact(content, pii=False), "queued", None, now()),
        )
        store.execute("INSERT INTO job_principals VALUES(?,?)", (jid, effective().id))
        pool.submit(work, jid)
        return jid

    @asynccontextmanager
    async def lifespan(app):
        engine.auth.validate()
        await asyncio.to_thread(engine.connectors.discover)
        # Never retry interrupted writes or sends automatically.
        store.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'", (now(),))
        store.execute("UPDATE jobs SET status='interrupted' WHERE status='running'")
        store.execute(
            "UPDATE outbox SET status='uncertain',error='Bridge or server restarted during send' "
            "WHERE status='claimed'"
        )
        store.execute(
            "UPDATE approvals SET status='uncertain',error='Server restarted during execution' "
            "WHERE status='executing'"
        )
        # Fixture state resets on process restart; old proposals must be re-planned.
        store.execute(
            "UPDATE approvals SET status='expired',error='Simulated workspace restarted; request again' "
            "WHERE status='pending' AND name != 'imessage_draft'"
        )
        if engine.mode == "demo":
            store.seed()
        for job in store.query("SELECT id FROM jobs WHERE status='queued'"):
            pool.submit(work, job["id"])
        yield
        pool.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title="Chief Of Staff", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.engine = store, engine

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "detail": redact(
                    [{k: v for k, v in error.items() if k not in {"input", "ctx"}} for error in exc.errors()]
                )
            },
            status_code=422,
        )

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = (request.url.hostname or "").lower()
        origin = request.headers.get("origin")
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return JSONResponse({"detail": "Chief Of Staff only accepts loopback hosts"}, status_code=403)
        if origin and origin not in {
            str(request.base_url).rstrip("/"),
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }:
            return JSONResponse({"detail": "Untrusted browser origin"}, status_code=403)
        context = None
        if request.url.path.startswith("/api"):
            try:
                principal = engine.auth.authenticate(request.headers.get("authorization", ""))
            except PermissionError as exc:
                engine.audit.append(
                    "anonymous", "http.authorization", request.url.path, "denied", {"reason": str(exc)}
                )
                return JSONResponse({"detail": str(exc)}, status_code=401)
            try:
                principal.require(route_capability(request.method, request.url.path))
            except PermissionError as exc:
                engine.audit.append(
                    principal.id, "http.authorization", request.url.path, "denied", {"reason": str(exc)}
                )
                return JSONResponse({"detail": str(exc)}, status_code=403)
            request.state.principal = principal
            context = CURRENT.set(principal)
            if request.method != "GET":
                engine.audit.append(
                    principal.id, "http.mutation", request.url.path, "requested", {"method": request.method}
                )
        try:
            response = await call_next(request)
            if context is not None and request.method != "GET":
                engine.audit.append(
                    principal.id,
                    "http.mutation",
                    request.url.path,
                    "success" if response.status_code < 400 else "denied",
                    {"method": request.method, "status": response.status_code},
                )
        finally:
            if context is not None:
                CURRENT.reset(context)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; script-src 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith(("/api", "/bridge")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "product": "Chief Of Staff"}

    def config():
        rows = store.query("SELECT value FROM settings WHERE key='bridge_heartbeat'")
        last = json.loads(rows[0]["value"]) if rows else None
        connected = False
        if last:
            from datetime import datetime, timezone

            connected = (datetime.now(timezone.utc) - datetime.fromisoformat(last["at"])).total_seconds() < 30
        return {
            "mode": engine.mode,
            "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "model_configured": bool(os.getenv("OPENAI_API_KEY")),
            "fixture_date": "2026-04-08",
            "timezone": os.getenv("COS_TIMEZONE", "America/New_York"),
            "imessage": {
                "enabled": bridge_enabled(),
                "allowlist": sorted(allowed_recipients()),
                "token_configured": bool(os.getenv("COS_BRIDGE_TOKEN")),
                "connected": connected,
                "heartbeat": last,
            },
            "mcp_servers": engine.connectors.servers,
            "services": [
                {"name": n, "status": "simulated"}
                for n in ["Gmail", "Calendar", "Drive", "Slack", "Linear", "GitHub", "Research"]
            ],
        }

    @app.get("/api/dashboard")
    def dashboard():
        return {
            **store.snapshot(),
            "config": config(),
            "security": {
                "authenticated": required(),
                "principal": effective().id,
                "roles": effective().roles,
                "capabilities": sorted({c for r in effective().roles for c in ROLE_CAPABILITIES[r]}),
                "separate_approver": required() or os.getenv("COS_REQUIRE_SEPARATE_APPROVER") == "true",
                "integrity": engine.audit.verify(),
                "records": engine.audit.records(30),
            },
            "jobs": store.query(
                "SELECT id,status,conversation_id,created_at FROM jobs ORDER BY created_at DESC LIMIT 50"
            ),
        }

    @app.get("/api/audit")
    def audit():
        return {"integrity": engine.audit.verify(), "records": engine.audit.records()}

    @app.get("/api/conversations/{cid}")
    def conversation(cid: str):
        if not store.query("SELECT id FROM conversations WHERE id=?", (cid,)):
            raise HTTPException(404, "Conversation not found")
        return {"messages": store.messages(cid)}

    @app.post("/api/chat", status_code=202)
    def chat(body: ChatBody):
        content = body.content.strip()
        if not content:
            raise HTTPException(422, "Message cannot be blank")
        cid = body.conversation_id
        if cid:
            if not store.query("SELECT id FROM conversations WHERE id=? AND channel='web'", (cid,)):
                raise HTTPException(404, "Web conversation not found")
        else:
            cid = store.conversation(content)
        # Do not allow unbounded work to accumulate behind a slow provider.
        if len(store.query("SELECT id FROM jobs WHERE status IN ('queued','running')")) >= 10:
            raise HTTPException(429, "Ten runs are already pending. Wait for one to finish.")
        return {"job_id": enqueue(cid, content), "conversation_id": cid}

    @app.get("/api/jobs/{jid}")
    def job(jid: str):
        rows = store.query("SELECT * FROM jobs WHERE id=?", (jid,))
        if not rows:
            raise HTTPException(404, "Job not found")
        item = rows[0]
        item["result"] = json.loads(item["result"]) if item["result"] else None
        return item

    @app.patch("/api/tasks/{tid}")
    def toggle_task(tid: str):
        if not store.execute(
            "UPDATE tasks SET status=CASE status WHEN 'done' THEN 'open' ELSE 'done' END WHERE id=?", (tid,)
        ):
            raise HTTPException(404, "Task not found")
        return {"ok": True}

    @app.delete("/api/memories/{mid}")
    def forget(mid: str):
        if not store.execute("DELETE FROM memories WHERE id=?", (mid,)):
            raise HTTPException(404, "Memory not found")
        return {"ok": True}

    @app.post("/api/approvals/{aid}")
    def decide(aid: str, body: Decision):
        # CAS ensures simultaneous clicks can't execute a side effect twice.
        with EXECUTION_LOCK:
            rows = store.query("SELECT * FROM approvals WHERE id=?", (aid,))
            if not rows:
                raise HTTPException(404, "Approval not found")
            try:
                engine.check_approval(rows[0], effective())
            except PermissionError as exc:
                engine.audit.append(effective().id, "approval.decision", aid, "denied", {"reason": str(exc)})
                raise HTTPException(403, str(exc)) from exc
            engine.audit.append(
                effective().id,
                "approval.decision",
                aid,
                "requested",
                {"tool": rows[0]["name"]},
            )
            status = "executing" if body.approve else "rejected"
            if not store.execute(
                "UPDATE approvals SET status=? WHERE id=? AND status='pending'", (status, aid)
            ):
                if not store.query("SELECT id FROM approvals WHERE id=?", (aid,)):
                    raise HTTPException(404, "Approval not found")
                raise HTTPException(409, "This proposal has already been decided")
            row = store.query("SELECT * FROM approvals WHERE id=?", (aid,))[0]
            if body.approve:
                result, error = engine.execute(
                    row["run_id"], row["name"], json.loads(row["arguments"]), approved=True
                )
                store.execute(
                    "UPDATE approvals SET status=?,result=?,error=? WHERE id=?",
                    ("failed" if error else "approved", json.dumps(result), error, aid),
                )
            remaining = store.query(
                "SELECT id FROM approvals WHERE run_id=? AND status='pending'", (row["run_id"],)
            )
            if not remaining:
                store.execute(
                    "UPDATE runs SET status='reviewed' WHERE id=? AND status='awaiting_approval'",
                    (row["run_id"],),
                )
            return {"approval": store.query("SELECT * FROM approvals WHERE id=?", (aid,))[0]}

    def authorize_bridge(request):
        token = os.getenv("COS_BRIDGE_TOKEN", "")
        actual = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not bridge_enabled() or len(token) < 24 or not hmac.compare_digest(actual, token):
            engine.audit.append("anonymous", "bridge.authorization", request.url.path, "denied")
            raise HTTPException(401, "Bridge disabled or token invalid (minimum 24 characters)")
        if request.url.path != "/bridge/heartbeat":
            engine.audit.append("imessage-bridge", "bridge.request", request.url.path, "authenticated")

    @app.post("/bridge/heartbeat")
    def heartbeat(request: Request, body: Heartbeat):
        authorize_bridge(request)
        store.execute(
            "INSERT OR REPLACE INTO settings VALUES('bridge_heartbeat',?)",
            (json.dumps({"at": now(), "status": body.status[:200]}),),
        )
        return {"ok": True}

    @app.post("/bridge/inbound", status_code=202)
    def inbound(request: Request, body: Inbound):
        authorize_bridge(request)
        if body.sender not in allowed_recipients():
            raise HTTPException(403, "Sender is not allowlisted")
        if body.self_command:
            if body.sender != os.getenv("COS_IMESSAGE_SELF_HANDLE", "").strip():
                raise HTTPException(403, "Self-chat commands require the exact configured self handle")
            if store.query(
                "SELECT id FROM outbox WHERE recipient=? AND content=? LIMIT 1", (body.sender, body.content)
            ):
                return {"duplicate": True, "reason": "outgoing assistant echo"}
        if not body.content.strip().lower().startswith("/cos "):
            raise HTTPException(422, "Only explicit /cos commands are accepted")
        if not body.content[5:].strip():
            raise HTTPException(422, "Command cannot be blank")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT conversation_id FROM inbox WHERE external_id=?", (body.external_id,)
            ).fetchone()
            if old:
                return {"duplicate": True, "conversation_id": old["conversation_id"]}
            convo = db.execute(
                "SELECT id FROM conversations WHERE channel='imessage' AND recipient=?", (body.sender,)
            ).fetchone()
            cid = convo["id"] if convo else uid()
            if not convo:
                db.execute(
                    "INSERT INTO conversations VALUES(?,?,?,?,?)",
                    (cid, "iMessage · " + body.sender, "imessage", body.sender, now()),
                )
            db.execute(
                "INSERT INTO inbox VALUES(?,?,?,?,?)",
                (body.external_id, body.sender, redact(body.content, pii=False), cid, now()),
            )
            jid = uid()
            db.execute("INSERT INTO job_principals VALUES(?,?)", (jid, "imessage-bridge"))
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?)",
                (jid, cid, redact(body.content[5:].strip(), pii=False), "queued", None, now()),
            )
        pool.submit(work, jid)
        return {"job_id": jid, "conversation_id": cid, "duplicate": False}

    @app.post("/bridge/outbox/claim")
    def claim(request: Request):
        authorize_bridge(request)
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM outbox WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return {"message": None}
            item = dict(row)
            if item["recipient"] not in allowed_recipients():
                db.execute(
                    "UPDATE outbox SET status='blocked',error='Recipient removed from allowlist' WHERE id=?",
                    (item["id"],),
                )
                return {"message": None}
            db.execute("UPDATE outbox SET status='claimed' WHERE id=?", (item["id"],))
            return {"message": item}

    @app.post("/bridge/outbox/{oid}/ack")
    def ack(oid: str, request: Request, body: Ack):
        authorize_bridge(request)
        if body.status not in {"accepted", "uncertain"}:
            raise HTTPException(422, "Use accepted or uncertain; Messages does not verify delivery")
        if not store.execute(
            "UPDATE outbox SET status=?,error=? WHERE id=? AND status='claimed'",
            (body.status, redact(body.error), oid),
        ):
            raise HTTPException(409, "Outbox item not claimed or already acknowledged")
        return {"ok": True}

    @app.get("/api/setup/imessage")
    def setup():
        return {"content": (Path(__file__).resolve().parents[1] / "docs/IMESSAGE.md").read_text()}

    dist = Path(__file__).resolve().parents[1] / "frontend/dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(Path(__file__).resolve().parents[1] / "frontend/public/favicon.svg")

    @app.get("/")
    def index():
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return JSONResponse({"message": "Build frontend: cd frontend && npm ci && npm run build"})

    return app


app = create_app()
