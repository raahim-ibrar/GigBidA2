import { test, expect, type Page } from "@playwright/test";

test.skip(!process.env.GIGBID_TEST_DATABASE_URL, "Requires actual Postgres memory and worker control fixtures");
test.setTimeout(90000);

async function job(page: Page, title: string) {
  await page.goto("/inbox");
  await page.getByLabel("Job title", { exact: true }).fill(title);
  await page.getByLabel("Job description and screening questions").fill("Build a Python API.");
  await page.getByLabel("Maximum client budget").fill("30");
  await page.getByRole("button", { name: "Analyse and draft" }).click();
  await expect(page.getByRole("heading", { name: "Verified draft for review" })).toBeVisible({ timeout: 30000 });
}

test("confirm repeated edits, use the preference in a new run, and remove it", async ({ page }, info) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`memory-${crypto.randomUUID()}@example.org`);
  await page.getByLabel("Password", { exact: true }).fill("Memory browser development fixture password!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.goto("/portfolio");
  await page.getByLabel("Portfolio file").setInputFiles({ name: "memory-fixture.md", mimeType: "text/markdown", buffer: Buffer.from("I built a Python API.") });
  await page.getByLabel("Project or portfolio title").fill("Memory browser fixture");
  await page.getByRole("button", { name: "Upload evidence" }).click();
  await expect(page.getByTestId("source-status")).toHaveText("ready");
  for (let index = 0; index < 3; index++) {
    await job(page, `Memory development job ${index}`);
    await page.getByLabel("Edit cover letter").fill("Could we discuss scope?");
    await Promise.all([
      page.waitForResponse(response => response.url().endsWith("/api/approvals") && response.request().method() === "POST" && response.status() === 202),
      page.getByRole("button", { name: "Verify edits and request a new review" }).click(),
    ]);
  }
  await page.goto("/settings");
  const memory = page.getByRole("region", { name: "Memory settings" });
  const instruction = "Remove the opening sentence when the proposal remains coherent.";
  const candidate = memory.getByRole("article").filter({ hasText: instruction });
  await expect(candidate).toContainText("3 distinct drafts");
  await candidate.getByRole("button", { name: "Confirm preference" }).click();
  await expect(memory.getByText("Style preference confirmed. New proposal runs can use it.")).toBeVisible();
  await page.reload();
  await expect(memory.getByRole("button", { name: "Remove preference", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("memory-settings.png"), fullPage: true });
  await job(page, "Job using a confirmed style preference");
  await page.getByText("Style preferences used in this run", { exact: true }).click();
  await expect(page.getByText(instruction, { exact: true })).toBeVisible();
  await page.goto("/settings");
  await memory.getByRole("button", { name: "Remove preference", exact: true }).click();
  await expect(memory.getByText("Memory removed from future proposal runs.")).toBeVisible();
  await page.reload();
  await expect(memory.getByText("No confirmed style preferences.")).toBeVisible();
});
