# Product architecture

Chief Of Staff extends the supplied orchestrator into a single-user local application. This is product documentation, separate from the original interview's human-authored design writeup.

## Product boundary

`backend.app` serves the actual product. The retained `backend.main` supplies a tool registry and regression harness. Its old chat/reset endpoints are not mounted in the product. This keeps compatibility checks useful without creating a route around the approval policy.

The React desk talks to one same-origin API. The production bundle is served by FastAPI. Development uses Vite's proxy. Browser origin and Host checks reject DNS rebinding/cross-site access from arbitrary web origins; optional API authentication is separate from mandatory bridge authentication. Binding to loopback is part of the deployment contract, not a substitute for multi-user authorization.

## Persistence and jobs

SQLite runs in WAL mode with per-operation connections and transactional writes. Conversations, messages, tasks, memories, runs, events, proposals, commands, outbox items, and background jobs survive page refreshes. The server accepts jobs before running them on a dedicated single-worker executor, so model latency does not block health or dashboard requests.

A process-wide execution lock serializes turns and approvals because the inherited mock services share mutable module state. Independent pure read batches within a turn use up to four workers. Mixed batches run in order. The system is deliberately single-process: do not start multiple uvicorn workers against this database. Scaling would require a coordinated worker queue and durable connector state.

Queued jobs resume after restart. Running jobs become interrupted rather than being replayed. A crash cannot safely prove whether a remote mutation succeeded. Claimed sends and executing approvals become uncertain. Pending non-iMessage proposals expire after restart and must be planned again, because mock state resets and live schemas may change. Pending iMessage drafts are revalidated against the current enablement and allowlist at approval time.

## Orchestration

The product uses the OpenAI Responses API. A routing call ranks the inherited compact capability cards; lexical matches provide fallback/recall. The model then sees a bounded schema subset, plus local tools and relevant live MCP tools. `find_tools` provides mid-turn recovery for omitted capabilities. Saved preferences are injected as bounded data excerpts, not system authority. Retrieved text and imported messages are marked as untrusted data.

Full results go into the journal. The compaction layer limits the result shown to the model to reduce context growth. Tool inputs are validated with their Pydantic models or remote JSON schemas. Tool errors return evidence to the model; provider-level failure returns a conservative reply and preserves the journal. Provider errors are recorded without echoing provider response bodies that may contain credentials.

Eight model execution steps, twelve actual tool invocations, and an 80-second scheduling deadline bound work. Router/provider calls and live tool sessions have timeouts. Pure read batches can execute concurrently; any mixed read/write batch remains sequential. Results and failures of identical signatures are cached for the turn. Budget exhaustion reports partial completion without making an extra unbounded synthesis call.

This is a tool orchestration system rather than a set of autonomous persona agents. Clear execution boundaries and reviewable actions matter more than introducing multiple model roles for their own sake.

## Approval boundary

Personal tasks and explicitly requested memory are reversible local actions. All simulated service mutations, native outgoing texts, and remote MCP tools not explicitly configured as read-only become proposals. Validation occurs before a proposal is created.

Approval uses an atomic pending-to-executing compare-and-swap and a process-wide lock. The stored name and arguments are executed exactly once per proposal; rejection prevents execution. Failure remains a failure and cannot be blindly approved again. Execution is journaled separately from the proposal. If a later step depends on the approved result, the user continues the conversation; the app does not silently replay the old plan.

Exactly-once side effects cannot be promised for third-party services or AppleScript. The app guarantees one execution attempt per approval in a healthy process and records uncertainty after crashes. An uncertain send requires manual inspection. There is no blind at-least-once retry of remote mutations.

## Native iMessage adapter

The bridge is a separate opt-in process. It opens Apple's Messages SQLite database read-only, scans new row IDs in bounded pages, accepts direct plain-text `/cos` commands from allowlisted handles, and submits them over token-authenticated loopback HTTP. Transactional external-ID deduplication prevents replay from creating duplicate jobs. The local cursor is replaced atomically after all accepted commands in a page are posted.

Assistant replies use the same proposal boundary. Approval creates an outbox record; the bridge atomically claims a queued record and uses fixed AppleScript with separate arguments. Successful process return means Messages accepted the request, not that delivery happened. Timeout/error and crash recovery favor uncertainty over duplicate texts.

The adapter skips attachments, group chats, old history, and SMS. For newer macOS text storage, it uses bounded typedstream decoding through pytypedstream and skips unknown/malformed archives. Optional self-chat commands require the exact configured self handle, and outbox echoes are suppressed to avoid feedback loops. Apple database/schema changes are a known integration boundary. macOS permissions and real recipient sending require an explicit operator setup and validation.

## Live MCP adapter

Configuration is read from an operator-owned file; the model cannot add servers or change URLs/tokens. Discovery loads limited pages of schemas and isolates connection failures. HTTPS is mandatory except for loopback; tokens are referenced by environment-variable name. Remote tool names are prefixed and hashed. A tool is a mutation unless its exact remote name is manually listed as read-only, regardless of server-supplied hints.

Sessions open per operation with bounded timeouts. This avoids long-lived connection lifecycle complexity and keeps failed writes from being retried implicitly, at the cost of connection latency. This version supports Streamable HTTP tool calls and bearer credentials, without OAuth negotiation, stdio, resources, prompts, or sampling.

## Demo and validation

Deterministic demo flows and OpenAI flows share the executor, persistence, proposals and journal. Demo mode labels fixture data; live MCP tools are labeled LIVE. A prompt instructs the model to prefer relevant live connectors and to separate simulated findings from real ones. This is not a proof of semantic correctness: tool schemas, approvals, tests, and honest status reporting reduce concrete failure modes, while users still review high-impact proposals.

The test suite exercises state changes, persistence, concurrent read scheduling, provider failure after a completed task, call budgets, schema validation, repeated approvals, restart uncertainty, browser boundary checks, sender allowlists, ingestion deduplication, outbox acknowledgements and fixed-script argv handling. Browser tests exercise the user-visible walkthrough and mobile overflow/navigation. A live Responses smoke test and real local MCP discovery/read test validate protocol integration beyond mocks.
