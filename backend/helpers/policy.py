"""Safety rails around tool execution.

Three jobs, all of them things a prompt alone does not reliably enforce:

1. Block a small number of destructive tools unless the user actually asked for
   that action. GOOGLEDRIVE_EMPTY_TRASH takes no arguments and permanently
   removes fixture data, so a model reaching for it while "cleaning up" is an
   unrecoverable mistake.
2. Stop retry loops. A tool that has already failed twice with the same
   arguments will fail a third time, and each attempt burns a step.
3. Refuse to re-run a write that may have already taken effect.
   `slack_send_message` appends to channel state before validating thread_ts,
   so a "failed" send has already posted; retrying double-posts.
4. Cap how often a single read tool runs in a turn, so the model filters a list
   it already has instead of re-querying once per candidate value.
5. Refuse a call that already *succeeded* with identical arguments. Observed in
   testing: the model filed the same Linear issue twice (creating both ENG-6 and
   ENG-7) and re-listed the same issues six times. For a write that is a
   correctness bug, not just wasted latency, so it is enforced here rather than
   left to the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.helpers import config
from backend.helpers.catalog import is_write
from backend.helpers.executor import is_non_idempotent, signature

# Tool -> the intent the user must have expressed for it to be allowed.
GUARDED: dict[str, tuple[str, ...]] = {
    "GOOGLEDRIVE_EMPTY_TRASH": ("empty the trash", "empty trash", "purge the trash"),
    "GOOGLEDRIVE_DELETE_DRIVE": ("delete the drive", "delete shared drive", "remove the drive"),
    "GOOGLECALENDAR_CLEAR_CALENDAR": ("clear my calendar", "clear the calendar", "wipe the calendar"),
    "GMAIL_REMOVE_LABEL": ("delete the label", "remove the label entirely", "delete label"),
    "github_mark_all_notifications_read": ("mark all", "all as read"),
}


@dataclass
class Policy:
    user_text: str
    attempts: dict[str, int] = field(default_factory=dict)
    failed: set[str] = field(default_factory=set)
    succeeded: set[str] = field(default_factory=set)
    per_tool: dict[str, int] = field(default_factory=dict)

    def check(self, name: str, arguments: dict) -> str | None:
        """Return a refusal message to feed back, or None to proceed."""
        phrases = GUARDED.get(name)
        if phrases:
            lowered = self.user_text.lower()
            if not any(p in lowered for p in phrases):
                return (
                    f"Refused: {name} is destructive and the user did not ask for it. "
                    "Do not call it again. Explain to the user what it would do instead."
                )

        key = signature(name, arguments)

        if key in self.succeeded:
            if is_non_idempotent(name):
                return (
                    f"Refused: {name} already completed successfully with these exact "
                    "arguments earlier in this turn. Repeating it would duplicate the "
                    "change. Use the result you already have."
                )
            return (
                f"Refused: {name} was already called with these exact arguments and its "
                "result is above. Use that result instead of fetching it again."
            )

        if not is_write(name):
            runs = self.per_tool.get(name, 0)
            if runs >= config.MAX_CALLS_PER_READ_TOOL:
                return (
                    f"Refused: {name} has already run {runs} times this turn. Its earlier "
                    "results are above and contain the fields you need -- filter and "
                    "summarise those rather than querying again."
                )

        used = self.attempts.get(key, 0)
        if used >= config.MAX_ATTEMPTS_PER_CALL:
            return (
                f"Refused: {name} has already been attempted {used} times with these exact "
                "arguments and failed each time. Change the arguments or tell the user it "
                "cannot be done."
            )
        if key in self.failed and is_non_idempotent(name):
            return (
                f"Refused: {name} may have partially taken effect on its earlier failed "
                "attempt, so it must not be retried blindly. Verify the current state or "
                "report what happened."
            )
        self.attempts[key] = used + 1
        self.per_tool[name] = self.per_tool.get(name, 0) + 1
        return None

    def record_failure(self, name: str, arguments: dict) -> None:
        self.failed.add(signature(name, arguments))

    def record_success(self, name: str, arguments: dict) -> None:
        self.succeeded.add(signature(name, arguments))
