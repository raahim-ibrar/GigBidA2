import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e", testMatch: "costs.spec.ts", workers: 1,
  use: { baseURL: "http://127.0.0.1:3002", channel: "chromium" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --port 3002", url: "http://127.0.0.1:3002",
    reuseExistingServer: false,
    env: { NEXT_PUBLIC_API_URL: "", GIGBID_TEST_DIST: ".next-costs" },
  },
});
