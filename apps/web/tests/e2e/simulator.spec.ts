import { test, expect } from "@playwright/test";

test.skip(!process.env.GIGBID_TEST_DATABASE_URL, "Requires isolated Postgres checkpoints");
test.setTimeout(90000);
test("recover simulator outage, approve a proposal, then import its client reply", async ({ page, request }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`sim-${crypto.randomUUID()}@example.org`);
  await page.getByLabel("Password", { exact: true }).fill("Browser simulator fixture password 123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.goto("/portfolio");
  await page.getByLabel("Portfolio file").setInputFiles({ name: "sim-fixture.md", mimeType: "text/markdown", buffer: Buffer.from("I built a Python API.") });
  await page.getByLabel("Project or portfolio title").fill("Synthetic simulator fixture");
  await page.getByRole("button", { name: "Upload evidence" }).click();
  await expect(page.getByTestId("source-status")).toHaveText("ready");
  await page.goto("/inbox");
  await page.getByRole("button", { name: "Connect student simulator" }).click();
  await expect(page.getByText("student simulator online", { exact: true })).toBeVisible();
  await page.getByLabel("Simulator job search").fill("document search");
  await page.getByRole("button", { name: "Search simulator jobs" }).click();
  await page.getByRole("link", { name: "Document Search for synthetic project 2", exact: true }).click();
  const account = await page.evaluate(async () => (await fetch("http://127.0.0.1:8002/api/auth/me", { credentials: "include" })).json());
  const headers = { Authorization: "Bearer browser_sim_only", "X-Tenant-ID": account.id };
  try {
    expect((await request.post("http://127.0.0.1:8086/admin/fault", { headers, data: { mode: "unavailable" } })).ok()).toBe(true);
    await expect(page.getByTestId("marketplace-outage")).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Start a new proposal run" }).click();
    await expect(page.getByRole("heading", { name: "Run needs attention" })).toBeVisible({ timeout: 30000 });
  } finally {
    await request.post("http://127.0.0.1:8086/admin/fault", { headers, data: { mode: "normal" } });
  }
  await page.getByRole("button", { name: "Retry failed step" }).click();
  await expect(page.getByRole("heading", { name: "Verified draft for review" })).toBeVisible({ timeout: 30000 });
  await page.reload();
  await page.getByRole("button", { name: "Approve and submit to simulator" }).click();
  await expect(page.getByRole("heading", { name: "Submitted to student simulator" })).toBeVisible({ timeout: 20000 });
  await page.goto("/settings");
  await page.getByRole("button", { name: "Sync simulator activity" }).click();
  await expect(page.getByRole("status")).toContainText("1 client messages");
  await page.goto("/messages");
  await page.getByRole("link", { name: "Document Search for synthetic project 2", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Verified reply for review" })).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Approve and send simulator reply" }).click();
  await expect(page.getByRole("heading", { name: "Reply sent to student simulator" })).toBeVisible({ timeout: 20000 });
});
