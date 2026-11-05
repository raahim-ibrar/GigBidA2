import { test, expect } from "@playwright/test";

test("upload source evidence, search it, and delete it", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`portfolio-${Date.now()}@example.org`);
  await page.getByLabel("Password", { exact: true }).fill("Browser portfolio fixture password 123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.getByRole("navigation").getByRole("link", { name: "Portfolio", exact: true }).click();
  await page.getByLabel("Portfolio file").setInputFiles({ name: "browser-fixture.md", mimeType: "text/markdown",
    buffer: Buffer.from("Built a Python FastAPI service with PostgreSQL for a retail client.") });
  await page.getByLabel("Project or portfolio title").fill("Browser development fixture");
  await page.getByLabel("Skills (comma separated)").fill("Python, FastAPI, PostgreSQL");
  await page.getByRole("button", { name: "Upload evidence" }).click();
  await expect(page.getByTestId("source-status")).toHaveText("ready");
  await page.getByLabel("Job requirement").fill("Python FastAPI API development");
  await page.getByRole("button", { name: "Search evidence", exact: true }).click();
  const results = page.getByRole("region", { name: "Evidence results" });
  await expect(results).toContainText("retail client");
  await expect(results).toContainText("browser-fixture.md");
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Confirm delete", exact: true }).click();
  await expect(page.getByText("No portfolio evidence yet.", { exact: false })).toBeVisible();
});
