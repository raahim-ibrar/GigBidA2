import { test, expect } from "@playwright/test";

test("navigation exposes the job inbox shell", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Job inbox" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox", exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("not implemented");
});

// These are deliberately pending, not passing placeholders for the five required user flows.
test.fixme("onboard a real user and upload a portfolio", async () => {});
test.fixme("approve a proposal and resume its durable graph", async () => {});
test.fixme("reject a proposal with a reason", async () => {});
test.fixme("edit a draft and re-check claims and compliance", async () => {});
test.fixme("show marketplace-unavailable banner and recover queued work", async () => {});
