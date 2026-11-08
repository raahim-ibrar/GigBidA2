import { test, expect, type Page } from "@playwright/test";

test.skip(!process.env.GIGBID_TEST_DATABASE_URL, "Requires disposable Postgres schema and deterministic worker fixtures");
test.setTimeout(60000);

async function prepare(page: Page, retryFixture = false) {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`proposal-${crypto.randomUUID()}@example.org`);
  await page.getByLabel("Password", { exact: true }).fill("Browser proposal fixture password 123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.goto("/portfolio");
  await page.getByLabel("Portfolio file").setInputFiles({ name: "proposal-fixture.md", mimeType: "text/markdown", buffer: Buffer.from("I built a Python API.") });
  await page.getByLabel("Project or portfolio title").fill("Proposal browser fixture");
  await page.getByRole("button", { name: "Upload evidence" }).click();
  await expect(page.getByTestId("source-status")).toHaveText("ready");
  await page.goto("/inbox");
  await page.getByLabel("Job title", { exact: true }).fill(retryFixture ? "Retry once fixture Python API" : "Python API development fixture");
  await page.getByLabel("Job description and screening questions").fill("Build a Python API.");
  await page.getByLabel("Maximum client budget").fill("30");
  await page.getByRole("button", { name: "Analyse and draft" }).click();
  await expect(page.getByRole("heading", { name: retryFixture ? "Run needs attention" : "Verified draft for review" })).toBeVisible({ timeout: 30000 });
}

test("recover a model outage from the saved checkpoint through an explicit retry", async ({ page }) => {
  await prepare(page, true);
  await expect(page.getByRole("button", { name: "Approve and save local draft" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "Retry failed step" })).toBeVisible();
  await page.getByRole("button", { name: "Retry failed step" }).click();
  await expect(page.getByRole("heading", { name: "Verified draft for review" })).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Approve and save local draft" }).click();
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toBeVisible({ timeout: 15000 });
});

test("regenerate a selected paragraph and review it before saving", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "Regenerate selected paragraph" }).click();
  await expect(page.getByLabel("Edit cover letter")).toHaveValue("Could we clarify priorities?", { timeout: 15000 });
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toHaveCount(0);
  await page.getByRole("button", { name: "Approve and save local draft" }).click();
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toBeVisible({ timeout: 15000 });
});

test("approved local proposals populate the pipeline and honest analytics on desktop and phone", async ({ page }, testInfo) => {
  await prepare(page);
  await page.getByRole("button", { name: "Approve and save local draft" }).click();
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toBeVisible({ timeout: 15000 });
  await page.goto("/pipeline");
  await expect(page.getByRole("region", { name: "drafted proposals", exact: true }).getByText("Local draft · not submitted")).toBeVisible();
  await expect(page.getByRole("region", { name: "submitted proposals", exact: true }).getByText("No proposals.")).toBeVisible();
  await page.goto("/analytics");
  await expect(page.getByText("No verified submission cohort is available.", { exact: false })).toBeVisible();
  await expect(page.getByRole("region", { name: "Run measurements" })).toContainText("Python API development fixture");
  await page.screenshot({ path: testInfo.outputPath("analytics-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Analytics", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("analytics-phone.png"), fullPage: true });
});

test("approve a verified local draft after a reload and preserve its save", async ({ page }) => {
  await prepare(page); await page.reload();
  await expect(page.getByRole("heading", { name: "Verified draft for review" })).toBeVisible();
  await page.getByLabel("I built a Python API. Portfolio evidence available.", { exact: true }).hover();
  await expect(page.getByRole("tooltip")).toContainText("proposal-fixture.md");
  await page.getByRole("button", { name: "Approve and save local draft" }).click();
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toBeVisible({ timeout: 15000 });
  await page.reload(); await expect(page.getByRole("heading", { name: "Saved local draft" })).toBeVisible();
});

test("reject a proposal only with a reason", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "Reject draft", exact: true }).click();
  await expect(page.getByText("Enter a rejection reason.", { exact: true })).toBeVisible();
  await page.getByLabel("Reason for rejection").fill("Scope does not fit my availability.");
  await page.getByRole("button", { name: "Reject draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("rejected", { timeout: 15000 });
});

test("edits are reverified and require a separate approval", async ({ page }) => {
  await prepare(page);
  await page.getByLabel("Edit cover letter").fill("Could we discuss scope?");
  await page.getByRole("button", { name: "Verify edits and request a new review" }).click();
  await expect(page.getByRole("heading", { name: "Verified draft for review" })).toBeVisible({ timeout: 15000 });
  await expect(page.getByLabel("Edit cover letter")).toHaveValue("Could we discuss scope?");
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toHaveCount(0);
  await page.getByRole("button", { name: "Approve and save local draft" }).click();
  await expect(page.getByRole("heading", { name: "Saved local draft" })).toBeVisible({ timeout: 15000 });
});

test("contact details in an edit are blocked before approval", async ({ page }) => {
  await prepare(page);
  await page.getByLabel("Edit cover letter").fill("Email me at fixture@example.org.");
  await page.getByRole("button", { name: "Verify edits and request a new review" }).click();
  await expect(page.getByRole("status")).toContainText("blocked", { timeout: 15000 });
  await expect(page.getByRole("button", { name: "Approve and save local draft" })).toHaveCount(0);
});
