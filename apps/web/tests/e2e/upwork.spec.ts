import { test, expect } from '@playwright/test';

test('Upwork controls label real jobs and revoke without exposing tokens', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByRole('button', { name: 'Create a new account' }).click();
  await page.getByLabel('Email', { exact: true }).fill(`upwork-${Date.now()}@example.org`);
  await page.getByLabel('Password', { exact: true }).fill('Upwork browser fixture password 123!');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Set up your profile' })).toBeVisible();
  let connected = true;
  await page.route('**/api/marketplace', async route => route.fulfill({ json: {
    mode: connected ? 'upwork' : 'manual', connected, available: connected,
    balance: null, synthetic: !connected, error: null, label: 'Upwork live account',
    upwork_connected: connected, capabilities: connected ? ['search_jobs', 'get_job'] : [],
    unavailable_capabilities: ['final_submission', 'send_message'], reconnect_required: false,
  }}));
  await page.route('**/api/marketplace/search', route => route.fulfill({ json: { jobs: [], provider: 'upwork', synthetic: false } }));
  await page.route('**/api/marketplace/upwork', route => {
    expect(route.request().method()).toBe('DELETE');
    expect(route.request().headers()['x-csrf-token']).toBeTruthy();
    connected = false;
    return route.fulfill({ json: { mode: 'manual', connected: false, available: false,
      upwork_connected: false, capabilities: [], unavailable_capabilities: [], synthetic: true } });
  });
  await page.goto('/settings');
  await expect(page.getByText('Upwork authorized', { exact: true })).toBeVisible();
  await page.getByLabel('Upwork job search').fill('Python');
  await page.getByRole('button', { name: 'Search Upwork jobs', exact: true }).click();
  await expect(page.getByText('0 real Upwork jobs saved to your inbox.')).toBeVisible();
  await page.getByRole('button', { name: 'Revoke Upwork connection' }).click();
  await expect(page.getByRole('button', { name: 'Revoke Upwork connection' })).toHaveCount(0);
  const id = '11111111-1111-4111-8111-111111111111';
  await page.route(`**/api/runs/${id}`, route => route.fulfill({ json: {
    id, job_id: id, kind: 'bid', status: 'pending_provider_confirmation', version: 1,
    snapshot: { marketplace_provider: 'upwork', provider_result: { preview_id: 'fixture-preview' } },
    steps: 3, tokens: 100, error: null, review: null, retryable: false,
  }}));
  await page.route(`**/api/runs/${id}/trace`, route => route.fulfill({ json: { trace_id: id, status: 'disabled', spans: 0 } }));
  await page.route(`**/api/runs/${id}/activity?*`, route => route.fulfill({ json: [] }));
  await page.goto(`/runs/${id}`);
  await expect(page.getByRole('heading', { name: 'Final confirmation remains on Upwork' })).toBeVisible();
  await expect(page.getByText('fixture-preview', { exact: true })).toBeVisible();
  await expect(page.getByText('Submitted to student simulator', { exact: true })).toHaveCount(0);
});
