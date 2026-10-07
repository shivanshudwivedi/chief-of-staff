"""Golden-set regression tests for the router.

Two properties are worth pinning, and both are checkable offline (no API key,
no network, deterministic), which is why they live here rather than in the
scenario suite:

  1. THE GATE IS NEVER WRONG. Skipping the Stage 1 router call is a latency
     optimisation; a gate that fires on the wrong service is a failed task. So
     every gate that fires must contain every cluster the prompt needs.
  2. FIXTURE NOUNS ARE RECOGNISED. The lexical layer exists to catch the
     concrete strings a summary-level router can miss.

The prompt set deliberately includes phrasings whose words are NOT in any
keyword list ("Ping the team...", "Where did I put the spreadsheet?"), because
the open question about a curated taxonomy is whether it generalises. Those
prompts are expected NOT to gate -- they fall through to the LLM router, which
is the correct outcome, and the assertion is only that they are never gated
*wrongly*.

The full-route recall number (81/81 with the LLM stage) is measured by
_work/routing_eval.py, which is not shipped because it costs an API call per
prompt.
"""

from __future__ import annotations

import unittest

from backend.helpers import config
from backend.helpers.catalog import tools_in
from backend.helpers.clusters import CLUSTERS_BY_ID
from backend.helpers.router import _gate, lexical_scores

# (prompt, clusters the task genuinely needs)
GOLDEN: list[tuple[str, set[str]]] = [
    ("What conversations do I have in Slack?", {"slack_conversations"}),
    ("Post 'deploy is green' to the engineering channel", {"slack_conversations"}),
    ("Who's in my Slack workspace?", {"slack_users"}),
    ("Show me my most recent emails", {"gmail_search"}),
    ("Draft a reply to the last email from ops", {"gmail_compose"}),
    ("What labels do I have set up?", {"gmail_labels"}),
    ("What's on my calendar next week?", {"calendar_read"}),
    ("Book a 30 minute sync with morgan on Tuesday", {"calendar_write"}),
    ("When am I free on Thursday?", {"calendar_availability"}),
    ("Delete budget_2025.xlsx from my Drive", {"drive_search"}),
    ("Share the launch brief with morgan@corp.com", {"drive_sharing"}),
    ("What Linear issues are open?", {"linear_issues"}),
    ("Add a comment to ENG-4", {"linear_comments"}),
    ("Which teams exist?", {"linear_org"}),
    ("Which pull requests are open?", {"gh_pull_requests"}),
    ("Are there any security vulnerabilities?", {"gh_security"}),
    ("Is CI passing?", {"gh_actions"}),
    ("Research best practices for launch checklists", {"perplexity_research"}),
    # cross-service: the gate must stay out of the way entirely
    ("Find the most recent email about the office move and post a summary to the "
     "engineering Slack channel", {"gmail_search", "slack_conversations"}),
    ("Research launch delays and file a Linear issue about it",
     {"perplexity_research", "linear_issues"}),
    ("Summarise the open PRs and post to Slack",
     {"gh_pull_requests", "slack_conversations"}),
    ("Take the launch brief from Drive and email it to ops",
     {"drive_search", "gmail_compose"}),
    # adversarial: no keyword overlap, expected to fall through to the LLM
    ("Ping the team about tomorrow's launch", {"slack_conversations"}),
    ("Where did I put the spreadsheet?", {"drive_search"}),
    ("Log a defect for the timeout we saw", {"linear_issues"}),
    ("Block out an hour for deep work on Monday", {"calendar_write"}),
]

NO_TOOL_PROMPTS = ["hi", "hello there", "thanks!", "what can you do?", "who are you?"]


class GateSafetyTests(unittest.TestCase):
    """A gate that fires must be right; a gate that abstains costs one call."""

    def test_no_gate_is_ever_wrong(self) -> None:
        for prompt, needed in GOLDEN:
            gated = _gate(lexical_scores(prompt))
            if gated is None:
                continue  # abstained -> Stage 1 handles it, which is fine
            missing = needed - set(gated)
            self.assertFalse(
                missing,
                f"gate fired on {prompt!r} but omitted {sorted(missing)}; "
                "skipping the router call must never lose a needed cluster",
            )

    def test_cross_service_prompts_never_gate(self) -> None:
        """The regression that nearly shipped: gating a two-service task to one."""
        for prompt, needed in GOLDEN:
            if len({CLUSTERS_BY_ID[c].service for c in needed}) > 1:
                self.assertIsNone(_gate(lexical_scores(prompt)), prompt)

    def test_conversational_prompts_route_to_nothing(self) -> None:
        for prompt in NO_TOOL_PROMPTS:
            self.assertEqual(lexical_scores(prompt), {}, prompt)
            self.assertIsNone(_gate(lexical_scores(prompt)), prompt)

    def test_gate_stays_within_its_tool_budget(self) -> None:
        for prompt, _ in GOLDEN:
            gated = _gate(lexical_scores(prompt))
            if gated:
                self.assertLessEqual(
                    len(tools_in(gated)), config.MAX_ROUTED_TOOLS, prompt
                )

    def test_gate_actually_fires_sometimes(self) -> None:
        """Guards against a change that silently disables the fast path."""
        fired = sum(1 for p, _ in GOLDEN if _gate(lexical_scores(p)))
        self.assertGreater(fired, 0, "the lexical fast path is never taken")


class LexicalSignalTests(unittest.TestCase):
    def test_fixture_nouns_are_recognised(self) -> None:
        """Concrete strings a summary-level router can miss."""
        for prompt, cluster in [
            ("Delete budget_2025.xlsx from my Drive", "drive_search"),
            ("What conversations do I have in Slack?", "slack_conversations"),
            ("Which pull requests are open?", "gh_pull_requests"),
            ("What Linear issues are open?", "linear_issues"),
        ]:
            self.assertIn(cluster, lexical_scores(prompt), prompt)

    def test_a_literal_tool_name_scores_decisively(self) -> None:
        scores = lexical_scores("call slack_send_message for me")
        self.assertEqual(next(iter(scores)), "slack_conversations")


if __name__ == "__main__":
    unittest.main()
