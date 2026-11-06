import { test, expect } from "@playwright/test";

function localInput(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

test("save local availability, find slots, reload and remove the window", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`calendar-${crypto.randomUUID()}@example.org`);
  await page.getByLabel("Password", { exact: true }).fill("Calendar browser development fixture password!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Set up your profile" })).toBeVisible();
  await page.goto("/settings");
  const calendar = page.getByRole("region", { name: "Local calendar" });
  const start = new Date(); start.setDate(start.getDate() + 1); start.setHours(10, 0, 0, 0);
  const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
  await calendar.getByLabel("Available from").fill(localInput(start));
  await calendar.getByLabel("Available until").fill(localInput(end));
  await calendar.getByRole("button", { name: "Save availability" }).click();
  await expect(calendar.getByText("Availability saved.", { exact: true })).toBeVisible();
  await calendar.getByLabel("Search from").fill(localInput(start));
  await calendar.getByLabel("Search until").fill(localInput(end));
  await calendar.getByRole("button", { name: "Find free slots" }).click();
  await expect(calendar.getByRole("region", { name: "Available interview slots" }).getByRole("listitem")).toHaveCount(7);
  await page.reload();
  await calendar.getByRole("button", { name: "Remove availability" }).click();
  await expect(calendar.getByText("No availability declared yet.")).toBeVisible();
});
