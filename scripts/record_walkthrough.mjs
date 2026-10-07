// Records actual browser interactions against an isolated, authenticated demo.
// Requires a built frontend, Playwright Chromium and ffmpeg. Never uses personal accounts.
import {
  chromium,
  expect,
} from "../frontend/node_modules/@playwright/test/index.mjs";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { randomBytes, createHash } from "node:crypto";
const root = fileURLToPath(new URL("..", import.meta.url));
const temporary = await mkdtemp(join(tmpdir(), "chief-recording-"));
const tokens = {
  operator: randomBytes(32).toString("hex"),
  reviewer: randomBytes(32).toString("hex"),
};
const registry = {
  principals: Object.entries(tokens).map(([id, token]) => ({
    id,
    roles: [id === "reviewer" ? "approver" : "operator"],
    tools: ["*"],
    token_sha256: createHash("sha256").update(token).digest("hex"),
  })),
};
const config = join(temporary, "principals.json");
await writeFile(config, JSON.stringify(registry), { mode: 0o600 });
const output = resolve(root, "docs/media");
await mkdir(output, { recursive: true });
await mkdir(resolve(root, "docs/images"), { recursive: true });
const port = 18842;
const baseURL = `http://127.0.0.1:${port}`;
const server = spawn(
  resolve(root, ".venv/bin/python"),
  [
    "-m",
    "uvicorn",
    "backend.app:app",
    "--host",
    "127.0.0.1",
    "--port",
    `${port}`,
  ],
  {
    cwd: root,
    stdio: ["ignore", "ignore", "pipe"],
    env: {
      ...process.env,
      COS_MODE: "demo",
      OPENAI_API_KEY: "",
      COS_DB_PATH: join(temporary, "chief.sqlite3"),
      COS_AUTH_CONFIG: config,
      COS_AUTH_REQUIRED: "true",
      COS_APPROVAL_SECRET: randomBytes(48).toString("hex"),
      COS_API_TOKEN: "",
      COS_MCP_CONFIG: "",
      COS_IMESSAGE_ENABLED: "false",
      COS_BRIDGE_TOKEN: "",
    },
  },
);
let serverError = "";
server.stderr.on("data", (d) => {
  serverError += d.toString();
});
let browser, context;
try {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(baseURL + "/health")).ok) break;
    } catch {}
    if (server.exitCode !== null) throw new Error(serverError);
    await new Promise((r) => setTimeout(r, 100));
  }
  browser = await chromium.launch();
  context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    recordVideo: { dir: temporary, size: { width: 1440, height: 1000 } },
  });
  const page = await context.newPage();
  await page.addInitScript(
    (token) => sessionStorage.setItem("cos-token", token),
    tokens.operator,
  );
  await page.goto(baseURL);
  await expect(page.getByLabel("Message Chief Of Staff")).toBeVisible();
  const caption = async (title, text, duration = 5500) => {
    console.log(title);
    await page.evaluate(
      ({ title, text }) => {
        let panel = document.getElementById("recording-caption");
        if (!panel) {
          panel = document.createElement("div");
          panel.id = "recording-caption";
          document.body.appendChild(panel);
        }
        panel.style.cssText =
          "position:fixed;z-index:99999;bottom:22px;left:280px;right:24px;background:#183d32f5;color:#fffefa;padding:18px 24px;border-radius:14px;box-shadow:0 8px 30px #0002;font:15px/1.5 system-ui;pointer-events:none";
        panel.replaceChildren();
        const heading = document.createElement("strong");
        heading.style.cssText =
          "display:block;font-size:18px;margin-bottom:4px";
        heading.textContent = title;
        const body = document.createElement("span");
        body.textContent = text;
        panel.append(heading, body);
      },
      { title, text },
    );
    await page.waitForTimeout(duration);
  };
  await caption(
    "Chief Of Staff · Operational walkthrough",
    "Actual browser recording · Authenticated demo · Simulated Gmail and Slack fixtures.",
  );
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.locator(".security-identity")).toContainText("operator");
  await caption(
    "1 · Server-owned permissions",
    "Signed in as operator. This role can run lookups and propose changes, but cannot approve them.",
  );
  await page.getByRole("button", { name: "My desk", exact: true }).click();
  await page
    .getByLabel("Message Chief Of Staff")
    .fill("Find revenue emails and post a summary to leadership Slack");
  await caption(
    "2 · One operational request",
    "Resolve the leadership channel, retrieve revenue emails, and prepare an update for review.",
    3500,
  );
  await page.getByLabel("Send message").click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "Review the exact message",
  );
  await caption(
    "3 · Bounded orchestration",
    "The shared executor authorizes each lookup and prepares a signed proposal. No Slack write has executed.",
  );
  await page.getByRole("button", { name: /^Approvals/ }).click();
  let proposal = page
    .locator(".proposal")
    .filter({ hasText: "pending" })
    .last();
  await expect(proposal).toContainText("slack send message");
  await caption(
    "4 · Exact arguments, before execution",
    "Review the proposed channel and message. The signature binds the action to its proposer and exact arguments.",
  );
  await proposal.getByRole("button", { name: "Approve action" }).click();
  await expect(page.getByRole("alert")).toContainText("actions.approve");
  await caption(
    "5 · Operator approval is denied",
    "The API returns 403. The proposal remains pending, and the denial is recorded in the security journal.",
  );
  await page.getByLabel("Dismiss error").click();
  // Switch actual credentials in the existing browser session, then reload the app.
  await page.evaluate(
    (token) => sessionStorage.setItem("cos-token", token),
    tokens.reviewer,
  );
  // addInitScript persists across navigations; replace the context script with reviewer via a new page.
  const reviewer = await context.newPage();
  await reviewer.addInitScript(
    (token) => sessionStorage.setItem("cos-token", token),
    tokens.reviewer,
  );
  // Context has no init scripts; page's operator script belongs only to the first page.
  await reviewer.goto(baseURL);
  await page.close();
  // Continue on reviewer page through a separate helper for captions.
  const reviewCaption = async (title, text, duration = 5500) => {
    console.log(title);
    await reviewer.evaluate(
      ({ title, text }) => {
        let panel = document.getElementById("recording-caption");
        if (!panel) {
          panel = document.createElement("div");
          panel.id = "recording-caption";
          document.body.appendChild(panel);
        }
        panel.style.cssText =
          "position:fixed;z-index:99999;bottom:22px;left:280px;right:24px;background:#183d32f5;color:#fffefa;padding:18px 24px;border-radius:14px;box-shadow:0 8px 30px #0002;font:15px/1.5 system-ui;pointer-events:none";
        panel.replaceChildren();
        const h = document.createElement("strong");
        h.style.cssText = "display:block;font-size:18px;margin-bottom:4px";
        h.textContent = title;
        const p = document.createElement("span");
        p.textContent = text;
        panel.append(h, p);
      },
      { title, text },
    );
    await reviewer.waitForTimeout(duration);
  };
  await reviewer.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(reviewer.locator(".security-identity")).toContainText(
    "reviewer",
  );
  await reviewCaption(
    "6 · A different principal reviews",
    "Signed in as reviewer with the approver role. The server rechecks both identities, tool scopes and the proposal signature.",
  );
  await reviewer.getByRole("button", { name: /^Approvals/ }).click();
  proposal = reviewer
    .locator(".proposal")
    .filter({ hasText: "pending" })
    .last();
  await proposal.getByRole("button", { name: "Approve action" }).click();
  await expect(
    proposal.getByRole("button", { name: "Approve action" }),
  ).toHaveCount(0);
  await reviewCaption(
    "7 · One approved execution attempt",
    "The stored message now executes against the Slack fixture. A repeated approval cannot post it again.",
  );
  await reviewer.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(reviewer.locator(".security-identity")).toContainText(
    "reviewer",
  );
  await expect(reviewer.getByText("Hash chain verified")).toBeVisible();
  await reviewCaption(
    "8 · Correlated audit evidence",
    "Actor, action, outcome and redacted payloads are recorded in an append-only hash chain. The UI verifies its retained history.",
  );
  const event = reviewer
    .locator(".security-records .event")
    .filter({ hasText: "GMAIL_FETCH_EMAILS" })
    .first();
  await event.locator("summary").click();
  await expect(event.locator("pre")).toContainText("[REDACTED:email]");
  await event.locator("pre").evaluate((pre) => {
    const text = pre.firstChild;
    const start = text.textContent.indexOf("[REDACTED:email]");
    const range = document.createRange();
    range.setStart(text, start);
    range.setEnd(text, start + 16);
    const container = pre.closest(".security-records");
    container.scrollTop +=
      range.getBoundingClientRect().top -
      container.getBoundingClientRect().top -
      120;
  });
  await reviewCaption(
    "9 · Sensitive data is masked before persistence",
    "Email addresses and detected credentials are redacted in audit evidence. Operational review payloads retain necessary recipients.",
  );
  await reviewer.evaluate(() =>
    document.getElementById("recording-caption")?.remove(),
  );
  await reviewer.screenshot({
    path: resolve(root, "docs/images/security.png"),
    fullPage: true,
  });
  await reviewCaption(
    "Implemented, tested, and inspectable",
    "Permissions · Separate approval gates · Sensitive-data redaction · Audit logging. See docs/SECURITY.md for code links and deployment limits.",
    6500,
  );
  const firstVideo = page.video();
  const secondVideo = reviewer.video();
  await context.close();
  context = null;
  const first = await firstVideo.path(),
    second = await secondVideo.path();
  const list = join(temporary, "concat.txt");
  await writeFile(list, `file '${first}'\nfile '${second}'\n`);
  const target = join(output, "operational-walkthrough.mp4");
  const encoded = spawnSync(
    "ffmpeg",
    [
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      list,
      "-c:v",
      "libx264",
      "-preset",
      "fast",
      "-crf",
      "25",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      target,
    ],
    { encoding: "utf8" },
  );
  if (encoded.status !== 0) throw new Error(encoded.stderr);
  console.log("Saved " + target);
} finally {
  if (context) await context.close();
  if (browser) await browser.close();
  server.kill("SIGTERM");
  await new Promise((r) => server.once("exit", r));
  await rm(temporary, { recursive: true, force: true });
}
