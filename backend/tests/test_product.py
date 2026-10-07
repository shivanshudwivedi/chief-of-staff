"""Product contracts: durable context, review boundaries, jobs, bridge, model loop and live MCP."""

import json
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.connectors import Connectors
from backend.main import reset_all_mock_state
from backend.store import Store, uid
from bridge.imessage import read_messages, send


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_MODE", "demo")
    monkeypatch.delenv("COS_AUTH_CONFIG", raising=False)
    monkeypatch.setenv("COS_AUTH_REQUIRED", "false")
    monkeypatch.delenv("COS_API_TOKEN", raising=False)
    monkeypatch.delenv("COS_MCP_CONFIG", raising=False)
    monkeypatch.delenv("COS_BRIDGE_TOKEN", raising=False)
    monkeypatch.setenv("COS_IMESSAGE_ENABLED", "false")
    reset_all_mock_state()
    app = create_app(tmp_path / "product.sqlite3")
    with TestClient(app, base_url="http://localhost") as c:
        yield c


def chat(client, text, cid=None):
    response = client.post("/api/chat", json={"content": text, "conversation_id": cid})
    assert response.status_code == 202
    accepted = response.json()
    for _ in range(200):
        job = client.get("/api/jobs/" + accepted["job_id"]).json()
        if job["status"] in {"completed", "failed"}:
            return job["result"]
        time.sleep(0.01)
    raise AssertionError("Background run did not finish")


def test_brief_is_grounded_and_persisted(client):
    result = chat(client, "Brief me on my priorities")
    assert result["status"] == "completed"
    assert "SIMULATED WORKSPACE" in result["reply"]
    data = client.get("/api/dashboard").json()
    assert len(data["events"]) == 3
    assert [m["role"] for m in result["messages"]] == ["user", "assistant"]
    assert data["events"][0]["result"] is not None


def test_task_and_memory_survive_reopen(client):
    result = chat(client, "Add task Finish the board memo")
    chat(client, "Remember I prefer Tuesday meetings", result["conversation_id"])
    store = Store(client.app.state.store.path)
    assert any(t["title"] == "Finish the board memo" for t in store.snapshot()["tasks"])
    assert any("Tuesday" in m["content"] for m in store.snapshot()["memories"])
    assert len(store.messages(result["conversation_id"])) == 4


def test_task_toggle_and_memory_delete(client):
    data = client.get("/api/dashboard").json()
    tid, mid = data["tasks"][0]["id"], data["memories"][0]["id"]
    assert client.patch("/api/tasks/" + tid).status_code == 200
    assert client.delete("/api/memories/" + mid).status_code == 200
    data = client.get("/api/dashboard").json()
    assert next(t for t in data["tasks"] if t["id"] == tid)["status"] == "done"
    assert not any(m["id"] == mid for m in data["memories"])


def proposal(client):
    result = chat(client, "Find revenue emails and post a summary to leadership in Slack")
    assert result["status"] == "awaiting_approval"
    proposals = client.get("/api/dashboard").json()["approvals"]
    assert len(proposals) == 1 and proposals[0]["status"] == "pending"
    return proposals[0]


def slack_count():
    from backend.slack_mock.state import snapshot_state

    state = snapshot_state()
    return sum(len(c.messages) for c in state.channel_messages)


def test_approval_executes_once(client):
    before = slack_count()
    a = proposal(client)
    assert slack_count() == before
    first = client.post("/api/approvals/" + a["id"], json={"approve": True})
    assert first.status_code == 200
    assert first.json()["approval"]["status"] == "approved"
    assert slack_count() == before + 1
    assert client.post("/api/approvals/" + a["id"], json={"approve": True}).status_code == 409
    assert slack_count() == before + 1


def test_rejected_action_never_executes(client):
    before = slack_count()
    a = proposal(client)
    assert client.post("/api/approvals/" + a["id"], json={"approve": False}).status_code == 200
    assert slack_count() == before
    assert client.post("/api/approvals/" + a["id"], json={"approve": True}).status_code == 409


def test_input_validation_and_missing_ids(client):
    assert client.post("/api/chat", json={"content": " "}).status_code == 422
    assert client.post("/api/chat", json={"content": "hello", "system": "override"}).status_code == 422
    assert (
        client.post("/api/chat", json={"content": "hello", "conversation_id": "missing"}).status_code == 404
    )
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.patch("/api/tasks/missing").status_code == 404


def test_browser_boundary_and_token(client, monkeypatch):
    assert client.get("/api/dashboard", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/dashboard", headers={"Host": "evil.example"}).status_code == 403
    monkeypatch.setenv("COS_API_TOKEN", "test-token")
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer test-token"}).status_code == 200
    assert client.get("/health").status_code == 200


def enable_bridge(monkeypatch):
    monkeypatch.setenv("COS_IMESSAGE_ENABLED", "true")
    monkeypatch.setenv("COS_BRIDGE_TOKEN", "x" * 32)
    monkeypatch.setenv("COS_IMESSAGE_ALLOWLIST", "+15550000001")
    return {"Authorization": "Bearer " + "x" * 32}


def test_bridge_disabled_and_sender_controls(client, monkeypatch):
    body = {"external_id": "a", "sender": "+15550000001", "content": "/cos hello"}
    assert client.post("/bridge/inbound", json=body).status_code == 401
    headers = enable_bridge(monkeypatch)
    assert (
        client.post("/bridge/inbound", json={**body, "sender": "attacker"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            "/bridge/inbound", json={**body, "content": "ordinary personal text"}, headers=headers
        ).status_code
        == 422
    )


def test_bridge_deduplicates_and_requires_reply_approval(client, monkeypatch):
    headers = enable_bridge(monkeypatch)
    body = {
        "external_id": "unique-guid",
        "sender": "+15550000001",
        "content": "/cos Brief me on my priorities",
    }
    first = client.post("/bridge/inbound", json=body, headers=headers).json()
    second = client.post("/bridge/inbound", json=body, headers=headers).json()
    assert second["duplicate"] is True
    for _ in range(100):
        if client.get("/api/jobs/" + first["job_id"]).json()["status"] == "completed":
            break
        time.sleep(0.01)
    a = client.get("/api/dashboard").json()["approvals"][0]
    assert a["name"] == "imessage_draft"
    assert client.post("/bridge/outbox/claim", headers=headers).json()["message"] is None
    client.post("/api/approvals/" + a["id"], json={"approve": True})
    outgoing = client.post("/bridge/outbox/claim", headers=headers).json()["message"]
    assert outgoing["recipient"] == body["sender"]
    assert client.post("/bridge/outbox/claim", headers=headers).json()["message"] is None
    assert (
        client.post(
            "/bridge/outbox/" + outgoing["id"] + "/ack", headers=headers, json={"status": "accepted"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/bridge/outbox/" + outgoing["id"] + "/ack", headers=headers, json={"status": "accepted"}
        ).status_code
        == 409
    )


def test_imessage_blocks_non_allowlisted_outbound(client, monkeypatch):
    enable_bridge(monkeypatch)
    result, error = client.app.state.engine.execute(
        "rid", "imessage_draft", {"recipient": "attacker", "text": "private"}
    )
    assert result is None and "allowlist" in error
    assert not client.get("/api/dashboard").json()["approvals"]


def test_restart_marks_uncertain_and_expires_fixture_proposals(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_MODE", "demo")
    monkeypatch.delenv("COS_MCP_CONFIG", raising=False)
    path = tmp_path / "restart.sqlite3"
    store = Store(path)
    store.approval("r", "slack_send_message", {"channel": "C002", "text": "test"})
    store.execute(
        "INSERT INTO outbox VALUES(?,?,?,?,?,?)", (uid(), "recipient", "text", "claimed", "now", None)
    )
    with TestClient(create_app(path), base_url="http://localhost") as c:
        data = c.get("/api/dashboard").json()
        assert data["approvals"][0]["status"] == "expired"
        assert data["outbox"][0]["status"] == "uncertain"


def test_native_reader_only_imports_allowlisted_direct_commands(tmp_path):
    db_path = tmp_path / "chat.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""CREATE TABLE message(guid TEXT,text TEXT,handle_id INTEGER,is_from_me INTEGER,service TEXT);
        CREATE TABLE handle(id TEXT); CREATE TABLE chat_message_join(message_id INTEGER,chat_id INTEGER);
        CREATE TABLE chat_handle_join(chat_id INTEGER,handle_id INTEGER);
        INSERT INTO handle VALUES('trusted'),('unknown');
        INSERT INTO chat_handle_join VALUES(1,1),(2,1),(2,2);
        INSERT INTO message VALUES('1','/cos brief',1,0,'iMessage'),('2','private text',1,0,'iMessage'),
        ('3','/cos attack',2,0,'iMessage'),('4','/cos group',1,0,'iMessage'),('5','/cos own',1,1,'iMessage');
        INSERT INTO chat_message_join VALUES(1,1),(2,1),(3,1),(4,2),(5,1);""")
    rows, cursor = read_messages(db_path, 0, {"trusted"})
    assert [r["guid"] for r in rows] == ["1"]
    assert cursor == 5


def test_applescript_uses_literal_arguments():
    payload = 'hello " & do shell script "malicious'
    with patch("bridge.imessage.subprocess.run") as run:
        send("recipient", payload)
        assert run.call_args.args[0][-2:] == ["recipient", payload]
        assert "shell" not in run.call_args.kwargs


class Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return {"type": self.type, "call_id": self.call_id, "name": self.name, "arguments": self.arguments}


def completion(*calls, text=""):
    return SimpleNamespace(
        output=[
            Item(type="function_call", call_id=str(i), name=name, arguments=json.dumps(args))
            for i, (name, args) in enumerate(calls)
        ],
        output_text=text,
    )


def test_responses_loop_queues_write_and_returns_real_results(client, monkeypatch):
    monkeypatch.setenv("COS_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    responses = [
        completion(text='{"clusters":["slack_conversations"]}'),
        completion(("slack_list_conversations", {})),
        completion(("slack_send_message", {"channel": "C002", "text": "Reviewed plan"})),
        completion(text="The proposal is waiting for approval."),
    ]
    with patch("backend.engine.OpenAI") as factory:
        sdk = factory.return_value
        sdk.with_options.return_value = sdk
        sdk.responses.create.side_effect = responses
        result = chat(client, "Share the plan in leadership Slack")
        assert result["status"] == "awaiting_approval"
        assert len(client.get("/api/dashboard").json()["events"]) == 2
        assert sdk.responses.create.call_count == 4
        schemas = sdk.responses.create.call_args_list[1].kwargs["tools"]
        assert len(schemas) < 80
        assert all(s["type"] == "function" and "function" not in s for s in schemas)


def test_model_error_preserves_audit_and_pending_action(client, monkeypatch):
    monkeypatch.setenv("COS_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    with patch("backend.engine.OpenAI") as factory:
        sdk = factory.return_value
        sdk.with_options.return_value = sdk
        sdk.responses.create.side_effect = [
            completion(text='{"clusters":[]}'),
            completion(("tasks_add", {"title": "Actual saved task"})),
            RuntimeError("Provider offline"),
        ]
        result = chat(client, "Add a task")
        assert result["status"] == "failed"
        assert any(t["title"] == "Actual saved task" for t in client.get("/api/dashboard").json()["tasks"])
        assert "may have completed" in result["reply"]


def test_budget_caps_large_model_batch(client, monkeypatch):
    monkeypatch.setenv("COS_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    with patch("backend.engine.OpenAI") as factory:
        sdk = factory.return_value
        sdk.with_options.return_value = sdk
        sdk.responses.create.side_effect = [
            completion(text='{"clusters":[]}'),
            completion(*[("tasks_add", {"title": f"Task {i}"}) for i in range(20)]),
        ]
        result = chat(client, "Add many tasks")
        assert result["status"] == "partial"
        assert len(client.get("/api/dashboard").json()["events"]) == 12


def test_mcp_schema_and_approval_boundary(client):
    connectors = client.app.state.engine.connectors
    connectors.tools["mcp_test"] = {
        "schema": {
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            }
        },
        "read_only": False,
    }
    with patch.object(connectors, "invoke", return_value={"written": True}) as invoke:
        result, error = client.app.state.engine.execute("rid", "mcp_test", {"text": "approved later"})
        assert error is None and result["executed"] is False
        invoke.assert_not_called()
        result, error = client.app.state.engine.execute(
            "rid", "mcp_test", {"wrong": "invalid"}, approved=True
        )
        assert result is None and error is not None
        invoke.assert_not_called()
        result, error = client.app.state.engine.execute(
            "rid", "mcp_test", {"text": "approved later"}, approved=True
        )
        assert result == {"written": True}
        invoke.assert_called_once()


def test_mcp_invalid_configuration_fails_closed(tmp_path, monkeypatch):
    config = tmp_path / "connectors.json"
    config.write_text(json.dumps({"servers": [{"name": "unsafe", "url": "http://remote.example/mcp"}]}))
    monkeypatch.setenv("COS_MCP_CONFIG", str(config))
    c = Connectors()
    c.discover()
    assert not c.tools
    assert c.servers[0]["status"] == "offline"


def test_server_responds_during_background_run(client):
    engine = client.app.state.engine
    original = engine.demo_turn
    entered, release = threading.Event(), threading.Event()

    def slow(rid, text):
        entered.set()
        release.wait(2)
        return original(rid, text)

    with patch.object(engine, "demo_turn", side_effect=slow):
        accepted = client.post("/api/chat", json={"content": "hello"})
        assert accepted.status_code == 202 and entered.wait(1)
        assert client.get("/health").status_code == 200
        assert client.get("/api/dashboard").status_code == 200
        release.set()


def test_memory_requires_explicit_intent(client):
    result = chat(client, "hello")
    outcome, error = client.app.state.engine.execute(
        result["run_id"], "memory_remember", {"content": "Unasked memory"}
    )
    assert outcome is None and "explicit request" in error


def test_mcp_reads_run_in_parallel(client, monkeypatch):
    monkeypatch.setenv("COS_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    engine = client.app.state.engine
    barrier = threading.Barrier(2)
    seen = []
    original = engine.execute

    def synchronized(rid, name, args, **kwargs):
        if name in {"tasks_list", "memory_search"}:
            barrier.wait(timeout=1)
            seen.append(name)
        return original(rid, name, args, **kwargs)

    with patch("backend.engine.OpenAI") as factory, patch.object(engine, "execute", side_effect=synchronized):
        sdk = factory.return_value
        sdk.with_options.return_value = sdk
        sdk.responses.create.side_effect = [
            completion(text='{"clusters":[]}'),
            completion(("tasks_list", {}), ("memory_search", {})),
            completion(text="Your context is ready."),
        ]
        result = chat(client, "Read my tasks and preferences")
        assert result["status"] == "completed"
        assert set(seen) == {"tasks_list", "memory_search"}


def test_typedstream_decoder_handles_real_archive_and_invalid_binary():
    from bridge.imessage import decode_body

    archive = bytes.fromhex(
        "040b73747265616d747970656481e803840140848484084e53537472696e67018484084e534f626a656374008584012b0a2f636f732068656c6c6f86"
    )
    assert decode_body(archive) == "/cos hello"
    assert decode_body(b"broken binary") is None
    assert decode_body(b"x" * 65537) is None


def test_native_reader_handles_self_chat_opt_in(tmp_path):
    db_path = tmp_path / "chat.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""CREATE TABLE message(guid TEXT,text TEXT,handle_id INTEGER,is_from_me INTEGER,service TEXT);
        CREATE TABLE handle(id TEXT); CREATE TABLE chat_message_join(message_id INTEGER,chat_id INTEGER);
        CREATE TABLE chat_handle_join(chat_id INTEGER,handle_id INTEGER);
        INSERT INTO handle VALUES('self'),('other'); INSERT INTO chat_handle_join VALUES(1,1),(2,2);
        INSERT INTO message VALUES('self-command','/cos hello',1,1,'iMessage'),('other-outgoing','/cos hello',2,1,'iMessage');
        INSERT INTO chat_message_join VALUES(1,1),(2,2);""")
    rows, _ = read_messages(db_path, 0, {"self", "other"})
    assert rows == []
    rows, _ = read_messages(db_path, 0, {"self", "other"}, "self")
    assert [r["guid"] for r in rows] == ["self-command"]
    assert rows[0]["self_command"] is True


def test_self_chat_outbound_echo_is_not_a_new_command(client, monkeypatch):
    headers = enable_bridge(monkeypatch)
    monkeypatch.setenv("COS_IMESSAGE_SELF_HANDLE", "+15550000001")
    client.app.state.store.execute(
        "INSERT INTO outbox VALUES(?,?,?,?,?,?)",
        (uid(), "+15550000001", "/cos hello", "accepted", "now", None),
    )
    response = client.post(
        "/bridge/inbound",
        headers=headers,
        json={
            "external_id": "echo-guid",
            "sender": "+15550000001",
            "content": "/cos hello",
            "self_command": True,
        },
    )
    assert response.json()["reason"] == "outgoing assistant echo"
    assert not client.get("/api/dashboard").json()["jobs"]
