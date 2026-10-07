# iMessage setup

This optional bridge runs on a Mac signed into Messages. Nothing in the normal app startup reads or sends your iMessages.

1. Copy `.env.example` to `.env`. Set these values:

   COS_IMESSAGE_ENABLED=true
   COS_IMESSAGE_ALLOWLIST=your-exact-phone-number-or-apple-id
   COS_BRIDGE_TOKEN=a-random-token-of-at-least-24-characters
   COS_URL=http://127.0.0.1:8000

   Generate a token with:
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'

   Use exact identifiers as Messages stores them, for example a phone number with its country code. Separate multiple identifiers with commas. Allowlist only the people you authorize to give your assistant commands. Anyone on the list can access the assistant's available context and create local tasks or memory.

2. In macOS System Settings → Privacy & Security → Full Disk Access, enable the terminal application that runs the bridge. This is required to open `~/Library/Messages/chat.db` in read-only mode. The app does not request this permission automatically.

3. Start Chief Of Staff. From the repository root run:

   uv run python bridge/imessage.py --check

   This validates configuration and database access without importing history or sending a text. Then start:

   uv run python bridge/imessage.py

4. From an allowlisted contact, send a new direct iMessage:

   /cos Brief me on my priorities

   Commands appear as an iMessage conversation on your desk. The response is drafted into Approvals. Click Approve action to queue it for the bridge. Reject leaves it unsent. On the first approved send, macOS may ask for Automation access to Messages; allow it under Privacy & Security → Automation.

5. Keep the bridge terminal and server running. Connectors shows a fresh heartbeat while the bridge is online. Stop the bridge with Ctrl+C. Set COS_IMESSAGE_ENABLED=false and restart the server to disable it.

## Boundaries

- First startup begins at the newest message, never backfills your history. A local cursor under data/ resumes future polling. Deleting the cursor intentionally starts fresh, without importing older messages.
- Only incoming, one-to-one iMessages with a non-empty plain-text body and the explicit /cos prefix are ingested. SMS, group chats, attachments and rich-only attributedBody messages are skipped. If a message is skipped, use a plain-text command or the web dashboard. The bridge depends on Apple's private Messages database layout and AppleScript support; macOS changes can require an adapter update.
- The native bridge never executes a shell command supplied by a message. Sending uses fixed AppleScript with separate argv values.
- Every outgoing text needs dashboard approval, including the assistant's own replies. Changing the recipient allowlist takes effect on the server after restart and the bridge after restart.
- Accepted means Messages accepted the AppleScript request. It is not a delivery receipt. An ambiguous timeout/crash produces an uncertain state that is never automatically retried. Inspect Messages before preparing another send. A claimed item stays claimed if the bridge dies until a server restart marks it uncertain.
- Bridge authentication uses a separate token. Its URL is restricted to loopback; the app does not expose a public webhook or tunnel.
- In OpenAI mode, imported commands and selected tool context are sent to OpenAI. The SQLite journal stores command text and assistant replies locally and is not encrypted by this app.
- Native sending has to be tested on your Mac with your allowlist and macOS permissions. Automated tests cover protocol handling and sender/recipient controls without touching personal Messages data.

Apple's permission references:
https://support.apple.com/en-hk/guide/mac-help/mchl108e1718/mac
https://support.apple.com/en-hk/guide/mac-help/mchlccb25729/mac
