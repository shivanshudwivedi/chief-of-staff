import { test, expect } from "@playwright/test";
test("desk, grounded brief, task, memory, reviewed proposal and connectors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A clear head. A capable right hand." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Find my focus" }).click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "SIMULATED WORKSPACE",
  );
  await page
    .getByLabel("Message Chief Of Staff")
    .fill("Add task Browser test priority");
  await page.getByLabel("Send message").click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "Browser test priority",
  );
  await page.getByRole("button", { name: "Tasks", exact: true }).click();
  const task = page
    .locator(".task-row")
    .filter({ hasText: "Browser test priority" })
    .first();
  await expect(task).toBeVisible();
  await task.click();
  await expect(task).toHaveClass(/done/);
  await page.getByRole("button", { name: "My desk", exact: true }).click();
  await page
    .getByLabel("Message Chief Of Staff")
    .fill("Remember I prefer clear walkthroughs");
  await page.getByLabel("Send message").click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "Remembered",
  );
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  await expect(page.locator(".memory-grid")).toContainText(
    "I prefer clear walkthroughs",
  );
  await page.getByRole("button", { name: "My desk", exact: true }).click();
  await page
    .getByLabel("Message Chief Of Staff")
    .fill("Find revenue emails and post a summary to leadership Slack");
  await page.getByLabel("Send message").click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "Review the exact message",
  );
  await page.getByRole("button", { name: /^Approvals/ }).click();
  const pending = page
    .locator(".proposal")
    .filter({ hasText: "pending" })
    .last();
  await expect(pending).toContainText("slack send message");
  await pending.getByRole("button", { name: "Approve action" }).click();
  await expect(
    pending.getByRole("button", { name: "Approve action" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.locator(".runs")).toContainText("reviewed");
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
  await expect(page.locator(".connector")).toHaveCount(8);
  await page.getByRole("button", { name: "Connect iMessage" }).click();
  await expect(page.getByRole("dialog")).toContainText("Full Disk Access");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.reload();
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  await expect(page.locator(".memory-grid")).toContainText(
    "I prefer clear walkthroughs",
  );
  expect(errors).toEqual([]);
});
test("mobile layout has no horizontal overflow and navigation works", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("Message Chief Of Staff")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByLabel("Open navigation").click();
  await page.getByRole("button", { name: "Connectors", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "iMessage", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
