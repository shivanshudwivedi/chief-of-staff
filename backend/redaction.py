"""Data minimization at audit and model-context boundaries, without altering executable proposals."""

from __future__ import annotations
import os
import re

SENSITIVE_KEYS = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|authorization|cookie|private_key|client_secret)(_|$)", re.I
)
SECRET_PATTERNS = [
    (
        re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----.*?-----END (?:[A-Z ]+)?PRIVATE KEY-----", re.S),
        "private-key",
    ),
    (
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
        ),
        "token",
    ),
    (re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_=.\-]{8,}", re.I), "authorization"),
    (
        re.compile(r"\b(password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[^\s,;]+", re.I),
        "credential",
    ),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "ssn"),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(
    r"(?<!\w)(?:\+1[ .-]?)?(?:\(\d{3}\)[ .-]?\d{3}[ .-]?\d{4}|\d{3}[ .-]\d{3}[ .-]\d{4}|\+\d{10,15})(?!\w)"
)


def redact(value, *, pii=True):
    """Copy structured data recursively. Credentials are always removed; audit PII is masked by default."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(key)).lower().replace("-", "_")
            result[key] = "[REDACTED:field]" if SENSITIVE_KEYS.search(normalized) else redact(item, pii=pii)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item, pii=pii) for item in value]
    if not isinstance(value, str):
        return value
    for name, secret in os.environ.items():
        if len(secret) >= 8 and SENSITIVE_KEYS.search(name.lower()):
            value = value.replace(secret, "[REDACTED:environment]")
    for pattern, category in SECRET_PATTERNS:
        value = pattern.sub(f"[REDACTED:{category}]", value)
    if pii:
        value = EMAIL.sub("[REDACTED:email]", value)
        value = PHONE.sub("[REDACTED:phone]", value)
    return value
