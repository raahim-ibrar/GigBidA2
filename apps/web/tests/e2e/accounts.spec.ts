import { test, expect } from "@playwright/test";

test("account registration, saved profile and a new sign-in persist settings", async ({ page }) => {
  const email = `freelancer-${Date.now()}@example.org`;
  const password = "GigBid browser test password 123!";
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.getByLabel("Display name").fill("Test Freelancer");
  await page.getByLabel("Profile type").selectOption("ai_ml");
  await page.getByLabel("Minimum hourly rate (USD)").fill("25.50");
  await page.getByLabel("Weekly Connects budget").fill("80");
  await page.getByLabel("Saved searches (one per line)").fill("Python automation\nRAG");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Job inbox", exact: true })).toBeVisible();
  await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
  await expect(page.getByLabel("Display name")).toHaveValue("Test Freelancer");
  await expect(page.getByLabel("Minimum hourly rate (USD)")).toHaveValue("25.50");
  await expect(page.getByLabel("Saved searches (one per line)")).toHaveValue("Python automation\nRAG");
});
