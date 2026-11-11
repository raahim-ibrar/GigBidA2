import { test, expect } from "@playwright/test";

test("persist a search schedule while clearly showing the missing marketplace connection", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`schedule-${crypto.randomUUID()}@example.org`);
  await page.getByLabel("Password", { exact: true }).fill("Browser schedule fixture password 123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.getByLabel("Display name").fill("Schedule fixture");
  await page.getByLabel("Saved searches (one per line)").fill("Python API\nData pipelines");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox", exact: true })).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByText("Saved searches fetch jobs from your connected simulator.", { exact: false })).toBeVisible();
  await page.getByLabel("Enable scheduled connection checks").check();
  await page.getByLabel("Check interval (minutes)").fill("15");
  await page.getByRole("button", { name: "Save search schedule" }).click();
  await expect(page.getByText("Search schedule saved.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Enable scheduled connection checks")).toBeChecked();
  await expect(page.getByLabel("Check interval (minutes)")).toHaveValue("15");
  await expect(page.getByText("waiting provider", { exact: true })).toBeVisible();
  await page.getByLabel("Enable scheduled connection checks").uncheck();
  await page.getByRole("button", { name: "Save search schedule" }).click();
  await expect(page.getByText("Search schedule saved.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Enable scheduled connection checks")).not.toBeChecked();
});
