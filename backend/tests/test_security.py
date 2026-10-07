"""Security regression contracts exercised through the real API and execution boundary."""

import hashlib
import json
import sqlite3
import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.audit import Audit
from backend.main import reset_all_mock_state
from backend.redaction import redact
from backend.security import Authorization
from backend.store import Store


@pytest.fixture
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_MODE", "demo")
    monkeypatch.setenv("COS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("COS_APPROVAL_SECRET", "test-approval-secret-with-at-least-32-characters")
    monkeypatch.setenv("COS_IMESSAGE_ENABLED", "false")
    monkeypatch.delenv("COS_MCP_CONFIG", raising=False)
    path = tmp_path / "auth.json"
    entries = [
        {
            "id": name,
            "roles": roles,
            "tools": tools,
            "token_sha256": hashlib.sha256((name + "-test-access").encode()).hexdigest(),
        }
        for name, roles, tools in [
            ("operator", ["operator"], ["*"]),
            ("reviewer", ["approver"], ["*"]),
            ("viewer", ["viewer"], []),
            ("admin", ["admin"], ["*"]),
            ("limited", ["operator"], ["tasks_*"]),
        ]
    ]
    path.write_text(json.dumps({"principals": entries}))
    monkeypatch.setenv("COS_AUTH_CONFIG", str(path))
    reset_all_mock_state()
    app = create_app(tmp_path / "secure.sqlite3")
    with TestClient(app, base_url="http://localhost") as client:
        yield client, path


def headers(id):
    return {"Authorization": "Bearer " + id + "-test-access"}


def propose(client, id="operator"):
    accepted = client.post(
        "/api/chat",
        headers=headers(id),
        json={"content": "Find revenue emails and post a summary to leadership Slack"},
    )
    assert accepted.status_code == 202
    for _ in range(200):
        result = client.get("/api/jobs/" + accepted.json()["job_id"], headers=headers(id)).json()
        if result["status"] in {"completed", "failed"}:
            assert result["result"]["status"] == "awaiting_approval"
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Job timed out")
    return client.get("/api/dashboard", headers=headers(id)).json()["approvals"][0]


def decide(client, id, proposal):
    return client.post("/api/approvals/" + proposal["id"], headers=headers(id), json={"approve": True})


def test_missing_and_invalid_credentials_fail_closed(secured):
    client, _ = secured
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers=headers("unknown")).status_code == 401
    assert client.post("/api/chat", headers={"X-Role": "admin"}, json={"content": "hello"}).status_code == 401


@pytest.mark.parametrize("role", ["viewer", "reviewer"])
def test_readers_cannot_start_runs(secured, role):
    client, _ = secured
    assert client.get("/api/dashboard", headers=headers(role)).status_code == 200
    assert client.post("/api/chat", headers=headers(role), json={"content": "Add task no"}).status_code == 403


def test_operator_proposes_reviewer_executes_exactly_once(secured):
    client, _ = secured
    proposal = propose(client)
    assert decide(client, "operator", proposal).status_code == 403
    assert decide(client, "viewer", proposal).status_code == 403
    assert decide(client, "reviewer", proposal).json()["approval"]["status"] == "approved"
    assert decide(client, "reviewer", proposal).status_code == 409
    audit = client.get("/api/audit", headers=headers("viewer")).json()
    assert audit["integrity"]["valid"]
    assert any(r["actor"] == "operator" and r["outcome"] == "denied" for r in audit["records"])
    assert any(
        r["actor"] == "reviewer" and r["action"] == "tool.complete" and r["outcome"] == "success"
        for r in audit["records"]
    )


def test_admin_cannot_approve_own_proposal(secured):
    client, _ = secured
    proposal = propose(client, "admin")
    response = decide(client, "admin", proposal)
    assert response.status_code == 403
    assert "different principal" in response.text
    assert decide(client, "reviewer", proposal).status_code == 200


@pytest.mark.parametrize("change", ["remove", "role", "scope"])
def test_revocation_is_checked_when_approving(secured, change):
    client, path = secured
    proposal = propose(client)
    config = json.loads(path.read_text())
    if change == "remove":
        config["principals"] = [p for p in config["principals"] if p["id"] != "operator"]
    else:
        entry = next(p for p in config["principals"] if p["id"] == "operator")
        entry["roles" if change == "role" else "tools"] = ["viewer"] if change == "role" else ["tasks_*"]
    path.write_text(json.dumps(config))
    assert decide(client, "reviewer", proposal).status_code == 403
    assert (
        client.app.state.store.query("SELECT status FROM approvals WHERE id=?", (proposal["id"],))[0][
            "status"
        ]
        == "pending"
    )


def test_payload_tampering_invalidates_signature(secured):
    client, _ = secured
    proposal = propose(client)
    client.app.state.store.execute(
        "UPDATE approvals SET arguments=? WHERE id=?",
        (json.dumps({"channel": "wrong-channel", "text": "Modified payload"}), proposal["id"]),
    )
    response = decide(client, "reviewer", proposal)
    assert response.status_code == 403 and "signature" in response.text


def test_tool_allowlist_is_enforced_even_for_direct_model_execution(secured):
    client, _ = secured
    engine = client.app.state.engine
    principal = Authorization().resolve("limited")
    with patch("backend.engine.execute_one") as invoke:
        result, error = engine.execute("run", "slack_list_conversations", {}, principal=principal)
    assert result is None and "allowlist" in error
    invoke.assert_not_called()
    assert not engine.tool_permitted("slack_send_message", principal)
    assert engine.tool_permitted("tasks_add", principal)


def test_scoped_reviewer_cannot_approve(secured):
    client, path = secured
    proposal = propose(client)
    config = json.loads(path.read_text())
    next(p for p in config["principals"] if p["id"] == "reviewer")["tools"] = ["tasks_*"]
    path.write_text(json.dumps(config))
    assert decide(client, "reviewer", proposal).status_code == 403


def test_credentials_cannot_be_saved_as_task_or_proposal(secured):
    client, _ = secured
    result, error = client.app.state.engine.execute(
        "run",
        "tasks_add",
        {"title": "password=very-private-password", "priority": "normal"},
        principal=Authorization().resolve("operator"),
    )
    assert result is None and "Credential-bearing" in error
    assert not any("private-password" in t["title"] for t in client.app.state.store.snapshot()["tasks"])


def test_destructive_tool_requires_user_intent(secured):
    client, _ = secured
    with patch("backend.engine.execute_one") as invoke:
        result, error = client.app.state.engine.execute(
            "run", "GOOGLEDRIVE_EMPTY_TRASH", {}, principal=Authorization().resolve("operator")
        )
    assert result is None and "explicit user intent" in error
    invoke.assert_not_called()


def test_redaction_recurses_masks_secrets_and_audit_pii(monkeypatch):
    monkeypatch.setenv("EXAMPLE_API_KEY", "environment-private-value")
    original = {
        "nested": [
            {
                "apiKey": "arbitrary-key",
                "authorization": "anything",
                "text": "environment-private-value sk-abcdef0123456789 person@example.com +15551234567 123-45-6789",
            }
        ]
    }
    cleaned = redact(original)
    encoded = json.dumps(cleaned)
    for secret in [
        "arbitrary-key",
        "anything",
        "environment-private-value",
        "sk-abcdef0123456789",
        "person@example.com",
        "+15551234567",
        "123-45-6789",
    ]:
        assert secret not in encoded
    assert original["nested"][0]["apiKey"] == "arbitrary-key"
    assert redact("person@example.com", pii=False) == "person@example.com"


def test_redaction_happens_before_persisting_event_and_audit(tmp_path):
    store = Store(tmp_path / "redaction.sqlite3")
    audit = Audit(store)
    args = {"api_key": "raw-key", "recipient": "person@example.com"}
    store.event("run", "example", args, {"password": "raw-password"}, "Bearer abcdef0123456789")
    audit.append("operator", "tool.complete", "run", "error", args)
    text = json.dumps(store.query("SELECT * FROM events") + store.query("SELECT * FROM audit_records"))
    for value in ["raw-key", "raw-password", "person@example.com", "abcdef0123456789"]:
        assert value not in text
    assert audit.verify()["valid"]


def test_journal_append_only_and_detects_modified_records(tmp_path):
    store = Store(tmp_path / "audit.sqlite3")
    audit = Audit(store)
    audit.append("operator", "example", "resource", "success")
    audit.append("reviewer", "example", "resource", "success")
    with pytest.raises(sqlite3.IntegrityError):
        store.execute("UPDATE audit_records SET outcome='forged'")
    with pytest.raises(sqlite3.IntegrityError):
        store.execute("DELETE FROM audit_records")
    store.execute("DROP TRIGGER audit_no_update")
    store.execute("UPDATE audit_records SET outcome='forged' WHERE seq=1")
    assert not audit.verify()["valid"]


def test_authenticated_mode_requires_persistent_signing_secret(secured, monkeypatch):
    monkeypatch.delenv("COS_APPROVAL_SECRET")
    with pytest.raises(ValueError, match="persistent"):
        Authorization().validate()


def test_invalid_validation_payload_does_not_echo_key(secured):
    client, _ = secured
    response = client.post(
        "/api/chat", headers=headers("operator"), json={"content": "hello", "api_key": "raw-sensitive-key"}
    )
    assert response.status_code == 422
    # Unknown keys have values in validation input; recursively recognize key-labelled secrets.
    assert "raw-sensitive-key" not in response.text
