"""The routing taxonomy: 191 tools grouped into 36 hand-curated clusters.

Why a curated taxonomy rather than embedding retrieval
------------------------------------------------------
The catalog is static, small and fully knowable at build time, so retrieval is
the wrong frame. A curated grouping is deterministic, reviewable in a diff,
testable without an API key, and -- decisively -- it can carry the
disambiguation rules that a similarity score cannot express. "GMAIL_REMOVE_LABEL
deletes a label workspace-wide, so it is *not* the tool for unlabelling one
message" is a sentence; it is not a point in vector space.

Each cluster carries:
    tools    -- the exact registered names (casing differs per service, so these
                are verbatim and never normalised)
    summary  -- one line answering "when does a request route here", shown to
                the Stage 1 router
    keywords -- lexical triggers for Stage 0, including fixture nouns that only
                exist in this mock (channel names, file names, issue prefixes)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cluster:
    id: str
    service: str
    summary: str
    tools: tuple[str, ...]
    keywords: tuple[str, ...] = field(default=())


CLUSTERS: tuple[Cluster, ...] = (
    # ---------------------------------------------------------------- gmail --
    Cluster(
        id="gmail_search",
        service="gmail",
        summary="Read, search or fetch emails, threads and attachments.",
        tools=(
            "GMAIL_FETCH_EMAILS",
            "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
            "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
            "GMAIL_LIST_THREADS",
            "GMAIL_GET_ATTACHMENT",
        ),
        keywords=(
            "email", "emails", "inbox", "gmail", "mail", "message", "thread",
            "attachment", "unread", "sender", "received", "correspondence",
        ),
    ),
    Cluster(
        id="gmail_compose",
        service="gmail",
        summary="Draft or reply to email, and manage or trash drafts and messages. NOTE: there is no send tool -- only drafts and replies.",
        tools=(
            "GMAIL_CREATE_EMAIL_DRAFT",
            "GMAIL_REPLY_TO_THREAD",
            "GMAIL_LIST_DRAFTS",
            "GMAIL_DELETE_DRAFT",
            "GMAIL_MOVE_TO_TRASH",
            "GMAIL_DELETE_MESSAGE",
        ),
        keywords=(
            "draft", "reply", "respond", "compose", "send email", "email them",
            "write to", "trash", "delete email",
        ),
    ),
    Cluster(
        id="gmail_labels",
        service="gmail",
        summary="Create, list, apply or remove Gmail labels on messages and threads.",
        tools=(
            "GMAIL_ADD_LABEL_TO_EMAIL",
            "GMAIL_CREATE_LABEL",
            "GMAIL_LIST_LABELS",
            "GMAIL_MODIFY_THREAD_LABELS",
            "GMAIL_PATCH_LABEL",
            "GMAIL_REMOVE_LABEL",
        ),
        keywords=("label", "labels", "tag email", "categorise", "categorize", "archive"),
    ),
    Cluster(
        id="gmail_contacts",
        service="gmail",
        summary="Look up the signed-in user's Gmail profile or their contacts.",
        tools=("GMAIL_GET_CONTACTS", "GMAIL_GET_PEOPLE", "GMAIL_GET_PROFILE"),
        keywords=("contact", "contacts", "my email address", "my profile", "who am i"),
    ),
    # ------------------------------------------------------------- calendar --
    Cluster(
        id="calendar_read",
        service="googlecalendar",
        summary="List, search or inspect calendar events and the current date.",
        tools=(
            "GOOGLECALENDAR_EVENTS_LIST",
            "GOOGLECALENDAR_FIND_EVENT",
            "GOOGLECALENDAR_EVENTS_INSTANCES",
            "GOOGLECALENDAR_GET_CURRENT_DATE_TIME",
        ),
        keywords=(
            "calendar", "event", "events", "meeting", "meetings", "agenda",
            "schedule for", "what's on", "upcoming", "appointment",
        ),
    ),
    Cluster(
        id="calendar_write",
        service="googlecalendar",
        summary="Create, update, move, delete or reschedule calendar events and their attendees.",
        tools=(
            "GOOGLECALENDAR_CREATE_EVENT",
            "GOOGLECALENDAR_UPDATE_EVENT",
            "GOOGLECALENDAR_PATCH_EVENT",
            "GOOGLECALENDAR_DELETE_EVENT",
            "GOOGLECALENDAR_QUICK_ADD",
            "GOOGLECALENDAR_EVENTS_MOVE",
            "GOOGLECALENDAR_REMOVE_ATTENDEE",
            "GOOGLECALENDAR_SYNC_EVENTS",
            "GOOGLECALENDAR_EVENTS_WATCH",
        ),
        keywords=(
            "schedule", "book", "set up a meeting", "create event", "invite",
            "reschedule", "cancel meeting", "move meeting", "30-minute", "attendee",
        ),
    ),
    Cluster(
        id="calendar_availability",
        service="googlecalendar",
        summary="Find free slots or query busy times across calendars before booking.",
        tools=("GOOGLECALENDAR_FIND_FREE_SLOTS", "GOOGLECALENDAR_FREE_BUSY_QUERY"),
        keywords=("free", "availability", "available", "busy", "free/busy", "open slot", "when can"),
    ),
    Cluster(
        id="calendar_admin",
        service="googlecalendar",
        summary="Manage calendars themselves: create, delete, duplicate, share (ACL) or configure settings. Not for events.",
        tools=(
            "GOOGLECALENDAR_LIST_CALENDARS",
            "GOOGLECALENDAR_GET_CALENDAR",
            "GOOGLECALENDAR_PATCH_CALENDAR",
            "GOOGLECALENDAR_CALENDARS_UPDATE",
            "GOOGLECALENDAR_CALENDARS_DELETE",
            "GOOGLECALENDAR_CALENDAR_LIST_INSERT",
            "GOOGLECALENDAR_CALENDAR_LIST_UPDATE",
            "GOOGLECALENDAR_CLEAR_CALENDAR",
            "GOOGLECALENDAR_DUPLICATE_CALENDAR",
            "GOOGLECALENDAR_ACL_PATCH",
            "GOOGLECALENDAR_LIST_ACL_RULES",
            "GOOGLECALENDAR_UPDATE_ACL_RULE",
            "GOOGLECALENDAR_SETTINGS_LIST",
            "GOOGLECALENDAR_SETTINGS_WATCH",
        ),
        keywords=("my calendars", "calendar settings", "share calendar", "calendar permission", "timezone"),
    ),
    # ---------------------------------------------------------------- drive --
    Cluster(
        id="drive_search",
        service="googledrive",
        summary="Find or download files and folders in Google Drive.",
        tools=("GOOGLEDRIVE_FIND_FILE", "GOOGLEDRIVE_FIND_FOLDER", "GOOGLEDRIVE_DOWNLOAD_FILE"),
        keywords=(
            "drive", "file", "files", "folder", "document", "spreadsheet", "xlsx",
            "doc", "pdf", "download", "find file", "delete file", ".xlsx", ".txt", ".md",
        ),
    ),
    Cluster(
        id="drive_write",
        service="googledrive",
        summary="Create, copy, edit or organise Drive files, folders and shared drives.",
        tools=(
            "GOOGLEDRIVE_CREATE_FILE",
            "GOOGLEDRIVE_CREATE_FILE_FROM_TEXT",
            "GOOGLEDRIVE_CREATE_FOLDER",
            "GOOGLEDRIVE_COPY_FILE",
            "GOOGLEDRIVE_EDIT_FILE",
            "GOOGLEDRIVE_CREATE_SHORTCUT_TO_FILE",
            "GOOGLEDRIVE_GENERATE_IDS",
            "GOOGLEDRIVE_FILES_MODIFY_LABELS",
            "GOOGLEDRIVE_CREATE_DRIVE",
            "GOOGLEDRIVE_DELETE_DRIVE",
            "GOOGLEDRIVE_EMPTY_TRASH",
        ),
        keywords=("create file", "new folder", "upload", "copy file", "rename", "empty trash"),
    ),
    Cluster(
        id="drive_sharing",
        service="googledrive",
        summary="Share Drive files with people, manage permissions, or comment on files.",
        tools=(
            "GOOGLEDRIVE_ADD_FILE_SHARING_PREFERENCE",
            "GOOGLEDRIVE_DELETE_PERMISSION",
            "GOOGLEDRIVE_CREATE_COMMENT",
            "GOOGLEDRIVE_CREATE_REPLY",
            "GOOGLEDRIVE_DELETE_COMMENT",
            "GOOGLEDRIVE_DELETE_REPLY",
        ),
        keywords=("share", "sharing", "permission", "access to", "comment on file"),
    ),
    # ---------------------------------------------------------------- slack --
    # send_message lives WITH list_conversations on purpose: channels are
    # addressed by ID only, so posting always needs the lookup in the same hop.
    Cluster(
        id="slack_conversations",
        service="slack",
        summary="List Slack channels and DMs, read their history or threads, search messages, and post a message to a channel.",
        tools=(
            "slack_list_conversations",
            "slack_conversations_history",
            "slack_get_full_conversation",
            "slack_get_thread",
            "slack_search_messages",
            "slack_send_message",
        ),
        keywords=(
            "slack", "channel", "channels", "conversation", "conversations", "post",
            "message", "dm", "thread", "engineering", "leadership", "war-room",
            "standup", "announce", "notify the team",
        ),
    ),
    Cluster(
        id="slack_users",
        service="slack",
        summary="Look up Slack workspace members, or check Slack connectivity/token status.",
        tools=("slack_list_users", "slack_users_info", "slack_health_check", "slack_token_status"),
        keywords=("slack user", "workspace member", "who is in slack", "slack profile"),
    ),
    # --------------------------------------------------------------- linear --
    Cluster(
        id="linear_issues",
        service="linear",
        summary="List, search, read, create or update Linear issues, their status and their labels.",
        tools=(
            "linear_list_issues",
            "linear_get_issue",
            "linear_create_issue",
            "linear_update_issue",
            "linear_list_issue_statuses",
            "linear_get_issue_status",
            "linear_list_issue_labels",
            "linear_create_issue_label",
        ),
        keywords=(
            "linear", "issue", "issues", "ticket", "tickets", "bug", "task", "backlog",
            "file an issue", "eng-", "gro-", "triage", "assigned to me", "sprint",
        ),
    ),
    Cluster(
        id="linear_comments",
        service="linear",
        summary="Read or add comments on a Linear issue.",
        tools=("linear_list_comments", "linear_create_comment"),
        keywords=("comment on issue", "add a note", "issue comment", "linear comment"),
    ),
    Cluster(
        id="linear_projects",
        service="linear",
        summary="List, read, create or update Linear projects and cycles.",
        tools=(
            "linear_list_projects",
            "linear_get_project",
            "linear_create_project",
            "linear_update_project",
            "linear_list_project_labels",
            "linear_list_cycles",
        ),
        keywords=("project", "projects", "roadmap", "cycle", "milestone", "initiative"),
    ),
    Cluster(
        id="linear_org",
        service="linear",
        summary="Look up Linear teams and users -- use to resolve a team key or a person's id.",
        tools=("linear_list_teams", "linear_get_team", "linear_list_users", "linear_get_user"),
        keywords=("team", "teams", "who is on", "linear user", "assignee"),
    ),
    Cluster(
        id="linear_docs",
        service="linear",
        summary="Linear documents, plus search over Linear's own product documentation.",
        tools=(
            "linear_list_documents",
            "linear_get_document",
            "linear_create_document",
            "linear_update_document",
            "linear_search_documentation",
        ),
        keywords=("linear document", "spec", "write-up", "linear docs"),
    ),
    # ----------------------------------------------------------- perplexity --
    Cluster(
        id="perplexity_research",
        service="perplexity",
        summary="Answer an external/world-knowledge question by searching the web with citations.",
        tools=("perplexity_search",),
        keywords=(
            "research", "look up", "search the web", "what is", "latest news",
            "find out about", "industry", "competitor", "best practices", "perplexity",
        ),
    ),
    # --------------------------------------------------------------- github --
    Cluster(
        id="gh_pull_requests",
        service="github",
        summary="List, read, create, review, update or merge GitHub pull requests, including PR review comments.",
        tools=(
            "github_list_pull_requests",
            "github_pull_request_read",
            "github_create_pull_request",
            "github_create_pull_request_with_copilot",
            "github_update_pull_request",
            "github_update_pull_request_branch",
            "github_merge_pull_request",
            "github_pull_request_review_write",
            "github_request_copilot_review",
            "github_add_comment_to_pending_review",
            "github_add_reply_to_pull_request_comment",
        ),
        keywords=("pull request", "pr", "prs", "merge", "review", "diff", "open prs"),
    ),
    Cluster(
        id="gh_issues",
        service="github",
        summary="List, read, create, update or comment on GitHub issues in a known repository.",
        tools=(
            "github_list_issues",
            "github_issue_read",
            "github_issue_write",
            "github_add_issue_comment",
            "github_sub_issue_write",
            "github_triage_issue",
            "github_list_issue_types",
        ),
        keywords=("github issue", "repo issue", "open issues", "close issue", "issue comment"),
    ),
    Cluster(
        id="gh_repos",
        service="github",
        summary="Create, fork or star GitHub repositories, and list starred repos.",
        tools=(
            "github_create_repository",
            "github_fork_repository",
            "github_star_repository",
            "github_unstar_repository",
            "github_list_starred_repositories",
        ),
        keywords=("repository", "repo", "fork", "star", "starred"),
    ),
    Cluster(
        id="gh_code",
        service="github",
        summary="Read or write repository files and branches when the path or branch is known.",
        tools=(
            "github_get_file_contents",
            "github_create_or_update_file",
            "github_delete_file",
            "github_push_files",
            "github_create_branch",
            "github_list_branches",
            "github_get_repository_tree",
        ),
        keywords=("file contents", "readme", "branch", "branches", "commit a file", "source code"),
    ),
    Cluster(
        id="gh_commits",
        service="github",
        summary="List or inspect commits on a repository or branch.",
        tools=("github_list_commits", "github_get_commit"),
        keywords=("commit", "commits", "recent changes", "changelog", "history"),
    ),
    Cluster(
        id="gh_releases",
        service="github",
        summary="GitHub releases and tags.",
        tools=(
            "github_list_releases",
            "github_get_latest_release",
            "github_get_release_by_tag",
            "github_list_tags",
            "github_get_tag",
        ),
        keywords=("release", "releases", "tag", "version", "changelog", "v1.0"),
    ),
    Cluster(
        id="gh_actions",
        service="github",
        summary="GitHub Actions: workflows, runs, job logs and CI status.",
        tools=(
            "github_actions_list",
            "github_actions_get",
            "github_actions_run_trigger",
            "github_get_job_logs",
        ),
        keywords=("ci", "workflow", "actions", "build", "pipeline", "job log", "failing build"),
    ),
    Cluster(
        id="gh_search",
        service="github",
        summary="Search GitHub broadly when no specific repository is named: code, issues, PRs, repos, users, orgs.",
        tools=(
            "github_search_code",
            "github_search_issues",
            "github_search_pull_requests",
            "github_search_repositories",
            "github_search_users",
            "github_search_orgs",
        ),
        keywords=("search github", "find repos", "search code", "across github"),
    ),
    Cluster(
        id="gh_notifications",
        service="github",
        summary="GitHub notification inbox: list, read, dismiss or subscribe.",
        tools=(
            "github_list_notifications",
            "github_get_notification_details",
            "github_dismiss_notification",
            "github_mark_all_notifications_read",
            "github_manage_notification_subscription",
            "github_manage_repository_notification_subscription",
        ),
        keywords=("notification", "notifications", "unread github", "subscribe", "watching"),
    ),
    Cluster(
        id="gh_security",
        service="github",
        summary="Security alerts and advisories: code scanning, Dependabot, secret scanning.",
        tools=(
            "github_list_code_scanning_alerts",
            "github_get_code_scanning_alert",
            "github_list_dependabot_alerts",
            "github_get_dependabot_alert",
            "github_list_secret_scanning_alerts",
            "github_get_secret_scanning_alert",
            "github_run_secret_scanning",
            "github_list_global_security_advisories",
            "github_get_global_security_advisory",
            "github_list_repository_security_advisories",
            "github_list_org_repository_security_advisories",
        ),
        keywords=(
            "security", "vulnerability", "vulnerabilities", "cve", "dependabot",
            "secret scanning", "code scanning", "advisory", "alert",
        ),
    ),
    Cluster(
        id="gh_labels",
        service="github",
        summary="Manage a GitHub repository's label catalogue.",
        tools=("github_list_label", "github_get_label", "github_label_write"),
        keywords=("github label", "repo labels"),
    ),
    Cluster(
        id="gh_discussions",
        service="github",
        summary="GitHub Discussions and their comments.",
        tools=(
            "github_list_discussions",
            "github_get_discussion",
            "github_get_discussion_comments",
            "github_list_discussion_categories",
        ),
        keywords=("discussion", "discussions", "q&a", "forum"),
    ),
    Cluster(
        id="gh_gists",
        service="github",
        summary="GitHub gists: list, read, create or update.",
        tools=("github_list_gists", "github_get_gist", "github_create_gist", "github_update_gist"),
        keywords=("gist", "gists", "snippet", "paste"),
    ),
    Cluster(
        id="gh_projects",
        service="github",
        summary="GitHub Projects (the planning boards), not repositories.",
        tools=("github_projects_list", "github_projects_get", "github_projects_write"),
        keywords=("github project", "project board", "kanban"),
    ),
    Cluster(
        id="gh_org",
        service="github",
        summary="The signed-in GitHub user, plus organisation teams and their members.",
        tools=("github_get_me", "github_get_teams", "github_get_team_members"),
        keywords=("my github", "github account", "org team", "team members"),
    ),
    Cluster(
        id="gh_copilot",
        service="github",
        summary="GitHub Copilot agent tasks and Copilot spaces.",
        tools=(
            "github_assign_copilot_to_issue",
            "github_get_copilot_job_status",
            "github_get_copilot_space",
            "github_list_copilot_spaces",
        ),
        keywords=("copilot", "copilot space", "agent task"),
    ),
    Cluster(
        id="gh_docs",
        service="github",
        summary="Search GitHub's own product documentation.",
        tools=("github_support_docs_search",),
        keywords=("github docs", "how do i in github", "github documentation"),
    ),
)


CLUSTERS_BY_ID: dict[str, Cluster] = {c.id: c for c in CLUSTERS}


# --- per-tool usage hints ----------------------------------------------------
# The generated docstrings describe *shape* but not *behaviour*. These sentences
# are the disambiguation rules from the fixture audit, appended to the tool
# description the model sees. Each one prevents a specific observed failure.
TOOL_HINTS: dict[str, str] = {
    # Gmail
    "GMAIL_FETCH_EMAILS": (
        "Default max_results is 1 -- always pass an explicit max_results (e.g. 25). "
        "The query supports only from:, to:, subject:, label: and in:. "
        "Operators like is:unread or has:attachment are NOT supported and match nothing; "
        "use label_ids=['UNREAD'] instead."
    ),
    "GMAIL_LIST_DRAFTS": "Default max_results is 1 and verbose defaults to false; pass both explicitly.",
    "GMAIL_CREATE_EMAIL_DRAFT": "There is no send-email tool. This creates a draft; say so rather than claiming an email was sent.",
    "GMAIL_REPLY_TO_THREAD": "Use for replying to an existing thread. There is no separate send tool.",
    "GMAIL_REMOVE_LABEL": (
        "DESTRUCTIVE: deletes the label from the entire workspace, stripping it from every message. "
        "To unlabel a single message use GMAIL_ADD_LABEL_TO_EMAIL's remove option or GMAIL_MODIFY_THREAD_LABELS."
    ),
    # Slack
    "slack_send_message": (
        "channel MUST be a channel ID (e.g. 'C001'), never a name or '#name'. "
        "Call slack_list_conversations first to resolve a name to an ID. "
        "Not idempotent -- never retry a failed send without checking whether it already posted."
    ),
    "slack_list_conversations": "Returns channel IDs and names; use this to resolve a channel name to the ID other Slack tools require.",
    "slack_conversations_history": "Returns the NEWEST messages first. Thread replies are not included.",
    "slack_get_full_conversation": "Returns the OLDEST messages first; pass include_threads=true to see thread replies.",
    # Calendar
    "GOOGLECALENDAR_CREATE_EVENT": (
        "Duration is additive from the start time via event_duration_hour + event_duration_minutes, "
        "which default to 0h30m. For a 30-minute meeting pass (0, 30); for 60 minutes pass (1, 0) -- "
        "passing hour=1 while leaving minutes at its default books 90 minutes. "
        "Use ISO datetimes with the -04:00 offset."
    ),
    "GOOGLECALENDAR_UPDATE_EVENT": "Full replace: any field you omit is cleared. Use PATCH_EVENT for a partial update.",
    "GOOGLECALENDAR_PATCH_EVENT": "Passing attendees replaces the whole attendee list and resets everyone's RSVP.",
    "GOOGLECALENDAR_FIND_EVENT": "Returns results under 'events'. Recurring-instance ids are synthetic and cannot be patched or deleted.",
    "GOOGLECALENDAR_EVENTS_LIST": "Uses camelCase args (calendarId, maxResults, timeMin, timeMax) and returns results under 'items'.",
    # Drive
    "GOOGLEDRIVE_FIND_FILE": (
        "Query syntax: \"name contains 'x'\", \"mimeType = 'x'\", \"fullText contains 'x'\". "
        "Pass includeItemsFromAllDrives=true to see shared-drive files. "
        "Returns an empty files list when nothing matches -- that means the file does not exist."
    ),
    "GOOGLEDRIVE_EMPTY_TRASH": "DESTRUCTIVE and unparameterised: permanently deletes everything in the trash. Only use if the user explicitly asks to empty the trash.",
    # Linear
    "linear_create_issue": (
        "team accepts a team id, a key like 'ENG', or a name like 'Engineering' -- no lookup call needed. "
        "state/assignee/project likewise accept display names. "
        "labels must already exist on the team, so omit labels unless you have confirmed the name."
    ),
    "linear_update_issue": "state takes the status display name (e.g. 'Done'), not a status id.",
    "linear_list_issues": (
        "Use query= for free-text search over issue titles and descriptions. "
        "One unfiltered call already returns every issue with its state, assignee and priority -- "
        "filter those results yourself rather than calling once per status."
    ),
    "linear_search_documentation": "Searches Linear's own product help articles, NOT your issues. For issues use linear_list_issues.",
    # GitHub
    "github_list_issues": "Defaults to state='open', which hides closed issues. Pass state='all' when the user asks about all issues.",
    "github_list_pull_requests": "Defaults to state='open', which hides closed and merged PRs.",
    "github_search_issues": "Naive substring search. GitHub qualifier syntax (is:open, label:bug, assignee:x) is NOT supported and matches nothing.",
    "github_get_repository_tree": "Passing an unknown tree_sha silently returns empty and pollutes state. Verify the branch with github_list_branches first.",
    "github_triage_issue": "Its triage_rationale argument is accepted but discarded. Use github_issue_write for a real update.",
}
