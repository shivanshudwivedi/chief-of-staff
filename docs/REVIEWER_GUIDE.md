# Reviewer guide

**[Start with the security implementation map](SECURITY.md#implementation-map).** It points directly to permissions, approval gates, sensitive-data redaction and audit logging, with regression evidence and deployment boundaries.

Chief Of Staff is a local assistant with 191 reusable simulated service tools, seven persistent local tools, optional live MCP servers, an OpenAI Responses orchestration loop, a React review desk and an opt-in native iMessage bridge. The seven bundled services are fixtures; their count does not imply 191 connected live integrations.

Run the credential-free demo using the [README](../README.md#quick-start). Try:

> Find revenue emails and post a summary to the leadership Slack channel

It resolves fixture channel IDs, retrieves revenue emails and prepares a message. Inspect exact arguments in **Approvals**, approve once, then open **Activity** to see executed results and the redacted security journal. For the role-separated version, follow [authenticated setup](SECURITY.md#enable-authenticated-mode): operator proposes, reviewer approves, self-approval is denied even for an admin.

The [architecture](ARCHITECTURE.md) explains bounded runs, sequential writes, deduplication and crash uncertainty. [iMessage setup](IMESSAGE.md) explains exact sender allowlists, `/cos` commands and review before sending. Native message delivery has not been validated on the user's personal account.

RBAC, separate approval checks, sensitive-data redaction and the hash-chained journal are implemented and tested. The project is intended for local use and review; describing it as independently verified production-grade would overstate the evidence.
