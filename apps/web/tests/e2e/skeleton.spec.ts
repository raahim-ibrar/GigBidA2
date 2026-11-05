import { test, expect } from "@playwright/test";

test("navigation exposes the job inbox and requires sign-in", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Job inbox" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox", exact: true })).toBeVisible();
  await expect(page.getByText("Sign in to add and review jobs.")).toBeVisible();
});

// These are deliberately pending, not passing placeholders for the five required user flows.
test.fixme("show marketplace-unavailable banner and recover queued work", async () => {});
