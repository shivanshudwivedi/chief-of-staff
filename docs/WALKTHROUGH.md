# A five-minute walkthrough

The app can be demonstrated without model credentials or Messages permissions. This is a suggested recording script; no video is represented as already recorded.

## 0:00–0:40 · The product

Open the desk. “Chief Of Staff brings priorities, persistent context, and reviewed actions into one local workspace. The demo is reproducible; these seven services use sample data. The local tasks and memory are real persistent records.”

Show the focus panel and the approval count. Mention that iMessage can act as another conversational frontend while the desk remains the review surface.

## 0:40–1:35 · A grounded brief

Click **Find my focus**. Show the assistant's local priorities and labeled simulated workspace findings. Open **Activity**, expand the latest run, and show `tasks_list`, `GMAIL_FETCH_EMAILS`, and `linear_list_issues` with their actual inputs/results.

“The activity panel gives a concrete execution trail. This is not a display of private model reasoning.”

## 1:35–2:20 · Persistent context

Return to **My desk** and send:

```text
Add task Review the launch memo
Remember I prefer concise updates
```

Show Tasks, toggle the task, show Memory, and refresh the page to demonstrate persistence. Preferences can be removed in Memory.

## 2:20–3:15 · The approval boundary

Send:

```text
Find revenue emails and post a summary to leadership Slack
```

Show the pending proposal, the resolved channel ID, and exact message text. Approve it, then inspect the separate execution event in Activity. Explain that the write changed the simulated fixture. A repeated approval cannot execute the same proposal again.

## 3:15–4:00 · Messaging and live services

Open Connectors and the iMessage setup dialog. Explain the `/cos` prefix, direct-chat allowlist, separate bridge token, Mac permissions, and reviewed outgoing replies. Native sending should only be demonstrated after configuring and validating your own Mac. Do not imply a disconnected bridge is live.

Optionally start the example MCP notes server, configure it, and restart the app. Show its discovered tools in Connectors. Model-backed mode can read actual notes or propose a note write using the same approval boundary.

## 4:00–5:00 · Architecture and tradeoffs

Show `backend/engine.py`: capability cards narrow the 191-tool fixture catalog before schemas, `find_tools` recovers missed capabilities, pure read batches overlap, and budgets prevent runaway loops. Show `backend/app.py`: durable jobs, approval compare-and-swap, and authenticated bridge routes. Show tests and CI.

Close with the implementation boundaries: single-user loopback deployment, explicitly simulated built-in accounts, opt-in live MCP servers, real OpenAI orchestration when configured, and native iMessage validation dependent on Mac permissions. Avoid claiming an unrecorded video, unavailable live account connection, delivery confirmation, or guaranteed model correctness.

## Recorded operational walkthrough

[Watch the actual browser recording](media/operational-walkthrough.mp4) (about 66 seconds, captioned, no audio). It demonstrates authenticated operator/reviewer separation on the simulated Gmail-to-Slack workflow, including a denied approval and redacted audit evidence.

To reproduce the recording after building the frontend and installing Playwright Chromium, install `ffmpeg` and run `node scripts/record_walkthrough.mjs`. The script starts an isolated authenticated demo server, generates temporary credentials, verifies UI outcomes, records browser interactions, and exports an MP4. It never reads personal Messages or connects to real services.
