"""Server-owned RBAC and capability policy. No client/model role headers grant permissions."""

from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

ROLE_CAPABILITIES = {
    "viewer": {"workspace.read", "audit.read"},
    "operator": {
        "workspace.read",
        "audit.read",
        "chat.execute",
        "tools.read",
        "tasks.write",
        "memory.write",
        "actions.propose",
    },
    "approver": {"workspace.read", "audit.read", "actions.approve"},
    "admin": {
        "workspace.read",
        "audit.read",
        "chat.execute",
        "tools.read",
        "tasks.write",
        "memory.write",
        "actions.propose",
        "actions.approve",
    },
}


@dataclass(frozen=True)
class Principal:
    id: str
    roles: tuple[str, ...]
    tools: tuple[str, ...] = ()

    def allows(self, capability):
        return any(capability in ROLE_CAPABILITIES.get(role, set()) for role in self.roles)

    def require(self, capability):
        if not self.allows(capability):
            raise PermissionError(f"Principal {self.id} lacks {capability}")

    def require_tool(self, name):
        if not any(fnmatchcase(name, pattern) for pattern in self.tools):
            raise PermissionError(f"Tool {name} is outside principal {self.id}'s allowlist")


DEVELOPMENT_OWNER = Principal("local-owner", ("admin",), ("*",))
BRIDGE = Principal("imessage-bridge", ("operator",), ("*",))
CURRENT = ContextVar("chief_principal", default=None)


def required():
    return os.getenv("COS_AUTH_REQUIRED", "false").lower() == "true" or bool(os.getenv("COS_AUTH_CONFIG"))


def effective():
    principal = CURRENT.get()
    if principal is not None:
        return principal
    return Principal("anonymous", (), ()) if required() else DEVELOPMENT_OWNER


class Authorization:
    def entries(self):
        path = os.getenv("COS_AUTH_CONFIG", "")
        if not path:
            return []
        # Reload for every decision: revoked identities and scopes do not linger in job snapshots.
        entries = json.loads(Path(path).read_text())["principals"]
        ids = set()
        for entry in entries:
            if (
                entry["id"] in ids
                or not entry["id"]
                or any(r not in ROLE_CAPABILITIES for r in entry["roles"])
            ):
                raise ValueError("Invalid or duplicate authorization principal")
            if entry["id"] in {"local-owner", "imessage-bridge"} or not re.fullmatch(
                r"[a-zA-Z0-9_-]{1,80}", entry["id"]
            ):
                raise ValueError("Principal ID is invalid or reserved")
            if not re.fullmatch(r"[a-f0-9]{64}", entry["token_sha256"]):
                raise ValueError("Principal tokens must be stored as SHA-256 digests")
            ids.add(entry["id"])
        return entries

    def validate(self):
        if required():
            if not self.entries():
                raise ValueError("Authenticated mode requires COS_AUTH_CONFIG with at least one principal")
            if len(os.getenv("COS_APPROVAL_SECRET", "")) < 32:
                raise ValueError(
                    "Authenticated mode requires a persistent COS_APPROVAL_SECRET of 32+ characters"
                )

    def authenticate(self, authorization):
        token = authorization.removeprefix("Bearer ")
        if required():
            if not authorization.startswith("Bearer ") or not token:
                raise PermissionError("Authentication required")
            digest = hashlib.sha256(token.encode()).hexdigest()
            for entry in self.entries():
                if hmac.compare_digest(entry["token_sha256"], digest):
                    return self.resolve(entry["id"])
            raise PermissionError("Invalid credentials")
        legacy = os.getenv("COS_API_TOKEN", "")
        if legacy and not hmac.compare_digest(token, legacy):
            raise PermissionError("API token required")
        return DEVELOPMENT_OWNER

    def resolve(self, id):
        if id == "imessage-bridge":
            patterns = tuple(
                s.strip()
                for s in os.getenv("COS_BRIDGE_TOOLS", "tasks_*,memory_*,imessage_*").split(",")
                if s.strip()
            )
            return Principal(id, ("operator",), patterns) if required() else BRIDGE
        if not required() and id == DEVELOPMENT_OWNER.id:
            return DEVELOPMENT_OWNER
        for entry in self.entries():
            if entry["id"] == id:
                return Principal(id, tuple(entry["roles"]), tuple(entry.get("tools", [])))
        raise PermissionError("Principal was revoked or is unknown")


def route_capability(method, path):
    if method == "GET":
        return "audit.read" if path.startswith("/api/audit") else "workspace.read"
    if method == "POST" and path == "/api/chat":
        return "chat.execute"
    if method == "POST" and path.startswith("/api/approvals/"):
        return "actions.approve"
    if method == "PATCH" and path.startswith("/api/tasks/"):
        return "tasks.write"
    if method == "DELETE" and path.startswith("/api/memories/"):
        return "memory.write"
    return "deny.unknown-route"
