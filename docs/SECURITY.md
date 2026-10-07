# Security implementation

Chief Of Staff enforces authorization and human review in code. This is a local, single-process application with tested controls—not an independently audited production security platform. The credential-free default is explicitly **trusted local development**. Enable authenticated mode for RBAC and separation of duties.

## Implementation map

| Requested control | Implementation | Regression evidence |
|---|---|---|
| Permissions | [`backend/security.py`](../backend/security.py): server-owned principals, role capabilities, hashed bearer credentials, tool allowlists, fresh policy resolution. [`backend/app.py`](../backend/app.py): API route authorization. [`backend/engine.py`](../backend/engine.py): authorization immediately before tool dispatch, including parallel workers. | Missing credentials, forbidden routes, tool scopes, revoked roles/scopes, scoped reviewers. |
| Approval gates | [`backend/engine.py`](../backend/engine.py): validated proposals and HMAC signatures over ID/run/tool/arguments/proposer; selected destructive actions require explicit intent. [`backend/app.py`](../backend/app.py): fresh proposer/approver checks, different approver in authenticated mode, pending-state compare-and-set, serialized execution. | Self-approval, payload tampering, denied operator approval, approval once, rejection, concurrent decisions. |
| Sensitive-data redaction | [`backend/redaction.py`](../backend/redaction.py): recursive sensitive-key masking, environment credential values, known token/authorization/private-key/SSN patterns, audit email/phone masking. [`backend/store.py`](../backend/store.py): redaction before tool-event persistence. Engine applies secret redaction to model context and rejects credential-bearing mutations. | Nested fields, environment secrets, log/result/error redaction, validation error filtering, credential-bearing writes denied. |
| Audit logging | [`backend/audit.py`](../backend/audit.py): append-only SQLite triggers, transactional hash chain, actor/action/resource/outcome, redacted payload. API and executor log authorization denials, mutation requests/outcomes, proposals/decisions, tool requests/results/errors, bridge requests. `GET /api/audit` and Activity expose the journal and verification. | Append/update/delete protection, modified-record detection, actor correlation, redaction before persistence. |

Run these contracts: `uv run pytest backend/tests/test_security.py backend/tests/test_product.py -q`.

## Roles and scopes

| Capability | Viewer | Operator | Approver | Admin |
|---|:---:|:---:|:---:|:---:|
| Read shared workspace and audit | ✓ | ✓ | ✓ | ✓ |
| Start orchestrated runs and read tools | | ✓ | | ✓ |
| Change local tasks / explicit preferences | | ✓ | | ✓ |
| Propose external mutations | | ✓ | | ✓ |
| Approve / reject external mutations | | | ✓ | ✓ |

Every tool also needs an explicit glob allowlist, such as `tasks_*`, `slack_*`, or a specific tool name. An empty list denies all tools. Roles and scopes come from the server's configuration, never prompt text, client role headers or model arguments. API task/memory edits use their role capability; orchestration and approvals additionally enforce tool scopes. All authenticated principals share one workspace; this is not tenant isolation or per-conversation ownership.

Policy is reloaded when authenticating, starting a queued job, executing each tool and approving. A revoked proposer cannot leave an executable proposal behind. Even an admin cannot approve their own proposal in authenticated mode. The iMessage service identity is an operator, cannot approve, and defaults to local task/memory/message tools; explicitly set `COS_BRIDGE_TOOLS` for any additional capabilities.

## Enable authenticated mode

```bash
uv run python scripts/setup_auth.py
```

This creates mode-0600 files in Git-ignored `data/security/`: `principals.json` contains token SHA-256 digests, `credentials.json` contains the separate users' actual access tokens, and `security.env` contains the three configuration values to copy into `.env`. Keep these files private. Give the operator and reviewer separate credentials; enter a user's token in the dashboard settings. Restart the server after setting:

```dotenv
COS_AUTH_REQUIRED=true
COS_AUTH_CONFIG=/absolute/path/to/data/security/principals.json
COS_APPROVAL_SECRET=<generated persistent secret of at least 32 characters>
```

Startup fails if authenticated mode lacks a valid registry or persistent signing secret. Use long random bearer tokens; this does not provide SSO, MFA or token expiry. Remove a principal from the registry to revoke it. Rotate the signing secret to invalidate outstanding proposals. Trusted local mode uses one admin identity and does not require a second person. Its process-random signing secret invalidates drafts across restarts; request a fresh proposal.

## One operational task

1. An **operator** asks: “Find revenue emails and post a summary to the leadership Slack channel.”
2. The executor authorizes `slack_list_conversations` and `GMAIL_FETCH_EMAILS`. The supplied workspace is explicitly simulated.
3. It validates a `slack_send_message` proposal, persists exact arguments and signs them. No Slack write has executed.
4. The operator's attempt to approve receives **403** and is recorded. A separate **reviewer** inspects the exact channel and message.
5. Review rechecks both identities, scopes and signature; one pending-state claim permits one execution attempt. A repeated click receives **409**.
6. Activity shows the operator's proposal, denied decision, reviewer's execution, redacted tool evidence, and a verified journal hash chain.

The same executor and review boundary apply in OpenAI mode and to configured live MCP mutations. The deterministic recording demonstrates fixtures; it does not claim to post into a real Slack account.

## Data and threat boundaries

Audit events and tool logs mask detected credentials, emails, phone numbers and SSNs **before persistence**. Ordinary conversation/model context retains operational email/phone values where required, while detected credentials are removed. Executable proposals and the outbox retain necessary recipients and message content so review and dispatch use the same payload; authenticated workspace readers can inspect them. Do not put arbitrary confidential data into a prompt: pattern-based redaction is not a complete PII classifier, encryption system or DLP service. Existing historical data is not retroactively rewritten.

SQLite UPDATE/DELETE triggers make the journal append-only through ordinary application access. Hash verification detects modification/reordering within the retained chain. A machine/database owner can drop triggers, rewrite the whole chain or truncate it: retain the journal head in a separate trusted system for stronger evidence. Records are not signed by an independent authority, and this is not a compliance certification. Local databases and operational payloads are not encrypted by this application; protect them with OS permissions and disk encryption.

Audit requests precede side effects, and failures stop execution. Completion logging cannot eliminate the crash window between an external effect and recording its result. The app records interrupted/uncertain outcomes and never blindly retries mutations. It promises one attempt per approved proposal in a healthy single process, not exactly-once delivery by remote services. Tool scopes do not constrain individual MCP arguments; review exact arguments and trust only configured servers. The configured read-only list is operator-trusted metadata.

Bind to loopback and run one uvicorn worker. Hosted multi-user use needs additional operational controls: SSO/token lifecycle, tenant/resource policy, TLS and deployment hardening, external audit retention and encryption. Authorization and logging choices follow [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) and [OWASP logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
