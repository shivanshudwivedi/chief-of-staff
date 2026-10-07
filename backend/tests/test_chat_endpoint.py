from __future__ import annotations

import unittest

from backend.main import app
from fastapi.testclient import TestClient


class ChatEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_chat_endpoint_exists_and_accepts_messages(self) -> None:
        response = self.client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        self.assertNotEqual(
            response.status_code, 404, "POST /chat should be registered"
        )
        self.assertNotEqual(
            response.status_code, 422, "POST /chat should accept the documented schema"
        )

    def test_chat_endpoint_rejects_malformed_payload(self) -> None:
        response = self.client.post("/chat", json={"messages": "nope"})
        self.assertEqual(response.status_code, 422)

    def test_chat_endpoint_is_implemented(self) -> None:
        # Was `assertEqual(status_code, 501)` against the starter stub; the file's
        # own comment says to delete that assertion once /chat is implemented.
        # Replaced rather than removed so the endpoint still has a liveness check.
        response = self.client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["messages"][-1]["role"], "assistant")
        self.assertIn("tool_calls", payload)


if __name__ == "__main__":
    unittest.main()
