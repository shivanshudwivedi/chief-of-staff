"""Tests for the chat orchestrator in backend/solution.py and backend/helpers/.

Split by cost. Everything except OrchestratorEndToEndTests runs offline, which
keeps the inner development loop fast; the end-to-end cases need OPENAI_API_KEY
and skip themselves without it.
"""

from __future__ import annotations

import os
import unittest

from backend.helpers.catalog import index, is_write, tools_in
from backend.helpers.clusters import CLUSTERS
from backend.helpers.compaction import compact
from backend.helpers.executor import ExecutionLog, execute_one, sanitize_arguments
from backend.helpers.policy import Policy
from backend.helpers.router import _gate, lexical_scores
from backend.helpers.schema import tool_schema, tools_payload
from backend.helpers.toolfinder import FIND_TOOLS, SCHEMA as FIND_TOOLS_SCHEMA, find
from backend.main import (
    app,
    get_openai_tools,
    get_tool_spec,
    list_available_tools,
    reset_all_mock_state,
)
from fastapi.testclient import TestClient


class TaxonomyTests(unittest.TestCase):
    def test_every_tool_is_in_exactly_one_cluster(self) -> None:
        assignments: dict[str, str] = {}
        for cluster in CLUSTERS:
            for name in cluster.tools:
                self.assertNotIn(name, assignments, f"{name} is in two clusters")
                assignments[name] = cluster.id
        self.assertEqual(set(assignments), set(list_available_tools()))

    def test_cluster_tool_names_are_real(self) -> None:
        registry = set(list_available_tools())
        for cluster in CLUSTERS:
            for name in cluster.tools:
                self.assertIn(name, registry, f"{name} is not a registered tool")

    def test_writes_are_classified(self) -> None:
        self.assertTrue(is_write("slack_send_message"))
        self.assertTrue(is_write("linear_create_issue"))
        self.assertFalse(is_write("slack_list_conversations"))
        self.assertFalse(is_write("GOOGLEDRIVE_FIND_FILE"))


class SchemaTests(unittest.TestCase):
    def test_required_list_is_truthful_not_forced(self) -> None:
        """main.py forces every property into `required`; we must not."""
        forced = {e["name"]: e for e in get_openai_tools(["linear_list_issues"])}
        self.assertTrue(forced["linear_list_issues"]["parameters"]["required"])
        mine = tool_schema("linear_list_issues")
        self.assertEqual(mine["function"]["parameters"]["required"], [])

    def test_genuinely_required_fields_survive(self) -> None:
        params = tool_schema("slack_send_message")["function"]["parameters"]
        self.assertEqual(sorted(params["required"]), ["channel", "text"])

    def test_defaults_are_stripped(self) -> None:
        def has_default(node) -> bool:
            if isinstance(node, dict):
                return "default" in node or any(has_default(v) for v in node.values())
            if isinstance(node, list):
                return any(has_default(v) for v in node)
            return False

        for schema in tools_payload(list_available_tools()):
            self.assertFalse(has_default(schema), schema["function"]["name"])

    def test_shape_is_chat_completions_nested(self) -> None:
        schema = tool_schema("perplexity_search")
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)
        self.assertIn("name", schema["function"])

    def test_routing_is_much_smaller_than_the_full_catalog(self) -> None:
        import json

        full = len(json.dumps(get_openai_tools()))
        routed = len(json.dumps(tools_payload(tools_in(["slack_conversations"]))))
        self.assertLess(routed * 20, full)


class ExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_mock_state()

    def test_nulls_are_stripped(self) -> None:
        self.assertEqual(sanitize_arguments('{"a": 1, "b": null}'), {"a": 1})
        self.assertEqual(sanitize_arguments(""), {})
        self.assertEqual(sanitize_arguments("not json"), {})

    def test_strict_mode_nulls_do_not_break_tools(self) -> None:
        """The landmine: 73 of 191 tools raise if a null reaches invoke()."""
        broken = []
        for entry in get_openai_tools():
            name = entry["name"]
            if get_tool_spec(name).args_model.model_json_schema().get("required"):
                continue  # has genuinely required fields; nulls are not the issue
            args = {p: None for p in entry["parameters"].get("properties", {})}
            outcome = execute_one(name, args, ExecutionLog())
            if outcome.error and "Invalid arguments" in outcome.error:
                broken.append((name, outcome.error))
        self.assertEqual(broken, [], "null-stripping should prevent validation errors")

    def test_result_envelope_is_unwrapped_once(self) -> None:
        outcome = execute_one("slack_list_conversations", {}, ExecutionLog())
        self.assertIsNone(outcome.error)
        self.assertIn("conversations", outcome.result)
        self.assertNotIn("result", outcome.result)

    def test_failures_are_captured_not_raised(self) -> None:
        log = ExecutionLog()
        outcome = execute_one("slack_send_message", {"channel": "engineering", "text": "x"}, log)
        self.assertIsNotNone(outcome.error)
        self.assertIn("Unknown Slack channel", outcome.error)
        self.assertEqual(log.count, 1, "a failed call must still be logged")

    def test_unknown_tool_is_reported(self) -> None:
        outcome = execute_one("no_such_tool", {}, ExecutionLog())
        self.assertIn("No such tool", outcome.error or "")


class PolicyTests(unittest.TestCase):
    def test_destructive_tool_is_blocked_without_intent(self) -> None:
        policy = Policy(user_text="tidy up my drive")
        self.assertIsNotNone(policy.check("GOOGLEDRIVE_EMPTY_TRASH", {}))

    def test_destructive_tool_is_allowed_when_asked_for(self) -> None:
        policy = Policy(user_text="please empty the trash in my drive")
        self.assertIsNone(policy.check("GOOGLEDRIVE_EMPTY_TRASH", {}))

    def test_successful_write_is_not_repeated(self) -> None:
        policy = Policy(user_text="file an issue")
        args = {"team": "ENG", "title": "x"}
        self.assertIsNone(policy.check("linear_create_issue", args))
        policy.record_success("linear_create_issue", args)
        refusal = policy.check("linear_create_issue", args)
        self.assertIn("already completed", refusal or "")

    def test_repeated_reads_are_capped(self) -> None:
        policy = Policy(user_text="list issues")
        for _ in range(3):
            self.assertIsNone(policy.check("linear_list_issues", {"state": _}))
        self.assertIsNotNone(policy.check("linear_list_issues", {"state": "another"}))

    def test_failed_non_idempotent_write_is_not_retried(self) -> None:
        policy = Policy(user_text="post to slack")
        args = {"channel": "C001", "text": "hi", "thread_ts": "bogus"}
        policy.check("slack_send_message", args)
        policy.record_failure("slack_send_message", args)
        self.assertIn("partially taken effect", policy.check("slack_send_message", args) or "")


class RouterTests(unittest.TestCase):
    """Stage 0 only -- deterministic and free, so it can be asserted exactly."""

    def test_single_service_prompts_skip_the_router_call(self) -> None:
        gated = _gate(lexical_scores("What conversations do I have in Slack?"))
        self.assertIsNotNone(gated)
        self.assertIn("slack_conversations", gated)

    def test_cross_service_prompts_do_not_gate(self) -> None:
        """The guard that stops the gate silently dropping half the task."""
        for prompt in (
            "Find the most recent email about timelines and post it to the Slack channel",
            "Research launch delays and file a Linear issue about it",
        ):
            self.assertIsNone(_gate(lexical_scores(prompt)), prompt)

    def test_fixture_nouns_are_recognised(self) -> None:
        self.assertIn("drive_search", lexical_scores("Delete budget_2025.xlsx from my Drive"))

    def test_greeting_routes_to_nothing(self) -> None:
        self.assertEqual(lexical_scores("hi there"), {})


class CompactionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_mock_state()

    def test_gmail_payload_is_projected(self) -> None:
        outcome = execute_one("GMAIL_FETCH_EMAILS", {"max_results": 25}, ExecutionLog())
        compacted = compact(outcome.result)
        first = compacted["messages"][0]
        self.assertIn("subject", first)
        self.assertNotIn("payload", first)

    def test_full_result_is_preserved_for_the_log(self) -> None:
        outcome = execute_one("GMAIL_FETCH_EMAILS", {"max_results": 25}, ExecutionLog())
        self.assertIn("payload", outcome.result["messages"][0])


class ToolFinderTests(unittest.TestCase):
    """The mid-turn escape hatch out of a routing mistake."""

    def test_it_finds_tools_for_a_plain_description(self) -> None:
        names, note = find("post a message to a slack channel", set())
        self.assertIn("slack_send_message", names)
        self.assertIn("slack_send_message", note)

    def test_it_does_not_reoffer_what_is_already_available(self) -> None:
        """Recall-biased by design, so it may surface adjacent clusters too --
        what it must never do is hand back a tool the model already has."""
        already = set(tools_in(["slack_conversations", "slack_users"]))
        names, _ = find("post a message to a slack channel", already)
        self.assertFalse(already.intersection(names))

    def test_it_reports_when_everything_matched_is_already_held(self) -> None:
        already = set(tools_in(["perplexity_research"]))
        names, note = find("search the web with perplexity", already)
        self.assertEqual(names, [])
        self.assertIn("already available", note)

    def test_unmatchable_need_is_reported_not_invented(self) -> None:
        names, note = find("qzxwv nonsense", set())
        self.assertEqual(names, [])
        self.assertIn("No tools matched", note)

    def test_schema_is_valid_and_not_a_registry_tool(self) -> None:
        self.assertEqual(FIND_TOOLS_SCHEMA["function"]["name"], FIND_TOOLS)
        self.assertNotIn(FIND_TOOLS, list_available_tools())


class ConversationMappingTests(unittest.TestCase):
    def test_caller_system_message_is_preserved(self) -> None:
        from backend.chat_schema import ChatMessage
        from backend.helpers.loop import _to_openai_messages

        out = _to_openai_messages([
            ChatMessage(role="system", content="Always answer in French."),
            ChatMessage(role="user", content="hi"),
        ])
        self.assertEqual(out[0]["role"], "system")
        self.assertIn("French", out[0]["content"])

    def test_long_histories_are_capped_but_keep_the_opening_turn(self) -> None:
        from backend.chat_schema import ChatMessage
        from backend.helpers import config
        from backend.helpers.loop import _to_openai_messages

        msgs = [ChatMessage(role="user", content="THE ORIGINAL GOAL")]
        msgs += [ChatMessage(role="user", content=f"m{i}") for i in range(40)]
        out = _to_openai_messages(msgs)
        self.assertLessEqual(len(out), config.MAX_HISTORY_MESSAGES)
        self.assertEqual(out[0]["content"], "THE ORIGINAL GOAL")
        self.assertEqual(out[-1]["content"], "m39")

    def test_tool_role_messages_survive_as_context(self) -> None:
        from backend.chat_schema import ChatMessage
        from backend.helpers.loop import _to_openai_messages

        out = _to_openai_messages([ChatMessage(role="tool", content='{"x":1}')])
        self.assertEqual(out[0]["role"], "assistant")
        self.assertIn('{"x":1}', out[0]["content"])


@unittest.skipUnless(os.getenv("OPENAI_API_KEY"), "needs OPENAI_API_KEY")
class OrchestratorEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_mock_state()
        self.client = TestClient(app)

    def _chat(self, text: str) -> dict:
        response = self.client.post("/chat", json={"messages": [{"role": "user", "content": text}]})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_greeting_calls_no_tools(self) -> None:
        payload = self._chat("hello")
        self.assertEqual(payload["tool_calls"], [])

    def test_single_service_lookup(self) -> None:
        payload = self._chat("What conversations do I have in Slack?")
        self.assertIn("slack_list_conversations", [c["name"] for c in payload["tool_calls"]])

    def test_conversation_is_echoed_with_the_reply_appended(self) -> None:
        payload = self._chat("What conversations do I have in Slack?")
        self.assertEqual(payload["messages"][0]["content"], "What conversations do I have in Slack?")
        self.assertEqual(payload["messages"][-1]["role"], "assistant")

    def test_reply_is_never_empty(self) -> None:
        payload = self._chat("hello")
        self.assertTrue(payload["messages"][-1]["content"].strip())

    def test_every_logged_call_is_a_real_tool_with_a_verdict(self) -> None:
        """The tool_calls log is what gets scored, so it must be well formed."""
        payload = self._chat("What conversations do I have in Slack?")
        registry = set(list_available_tools())
        for call in payload["tool_calls"]:
            self.assertIn(call["name"], registry, "only registry tools may be logged")
            self.assertIsInstance(call["arguments"], dict)
            self.assertTrue(call["result"] is not None or call["error"] is not None)

    def test_missing_file_is_reported_not_fabricated(self) -> None:
        """The file does not exist AND Drive has no delete tool. The contract is
        that we never claim the deletion happened -- phrasing is the model's
        choice, so assert on the claim rather than on wording."""
        payload = self._chat("Delete the file 'budget_2025.xlsx' from my Drive.")
        names = [c["name"] for c in payload["tool_calls"]]
        self.assertNotIn("GOOGLEDRIVE_EMPTY_TRASH", names)

        reply = payload["messages"][-1]["content"].lower().replace("\u2019", "'")
        self.assertIn("budget_2025", reply, "the reply should name the file it looked for")

        claimed_success = any(
            p in reply for p in ("i deleted", "has been deleted", "was deleted",
                                 "i've deleted", "i have deleted", "successfully deleted",
                                 "i removed", "has been removed")
        )
        self.assertFalse(claimed_success, f"must not fabricate a deletion: {reply}")

        acknowledged = any(
            p in reply for p in ("not find", "n't find", "no file", "not exist",
                                 "no matching", "doesn't have", "does not have",
                                 "unable", "can't", "cannot", "not available",
                                 "no such", "wasn't found", "not found")
        )
        self.assertTrue(acknowledged, f"must say why nothing happened: {reply}")


if __name__ == "__main__":
    unittest.main()
