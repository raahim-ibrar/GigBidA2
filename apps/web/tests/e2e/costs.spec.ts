import { test, expect } from "@playwright/test";

test("cost UI distinguishes partial estimates, tiny prices and unknown billing", async ({ page }) => {
  const costs = {
    currency: "USD", calls: 2, input_tokens: 1, output_tokens: 0,
    estimated_usd: .000000007, actual_api_usd: null, unknown_cost_calls: 1,
    unaccounted_tokens: 120, complete: false,
    basis: "Free-tier charges may be zero; local hardware and electricity excluded.",
    groups: [{ provider: "groq", model: "fixture", role: "writer", calls: 2,
      input_tokens: 1, output_tokens: 0, estimated_usd: .000000007, unknown_cost_calls: 1 }],
  };
  let zero = false;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/analytics")) {
      await route.fulfill({ json: {
        days: 30, run_count: 1, local_drafts: 0, charged_or_reserved_tokens: 121,
        measured_model_tokens: 1, inference_api_usd: null, connects_spent: null,
        submissions_with_known_spend: 0, provider_submissions: 0, category_rates: [],
        rejection_reasons: [], measurements: [], measurements_truncated: false,
        provider_connected: false, costs: zero ? { ...costs, estimated_usd: 0,
          actual_api_usd: 0, unknown_cost_calls: 0, unaccounted_tokens: 0,
          complete: true, groups: [] } : costs,
      } });
    } else {
      await route.fulfill({ status: 401, json: { detail: "Fixture: signed out" } });
    }
  });
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Inference cost estimate" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Inference cost breakdown" })).toContainText("<$0.00000001");
  await expect(page.getByText("Recorded API charges: Unknown.", { exact: false })).toBeVisible();
  await expect(page.getByText("Partial or unavailable estimate", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("2 recorded attempts", { exact: false })).toContainText("1 unpriced");
  zero = true;
  await page.getByRole("button", { name: "Refresh analytics" }).click();
  await expect(page.getByText("Recorded API charges: $0.", { exact: false })).toBeVisible();
  await expect(page.getByText("Recorded usage fully priced", { exact: false }).first()).toBeVisible();
});
