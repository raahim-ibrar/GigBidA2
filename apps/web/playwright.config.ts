import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
export default defineConfig({
  // Each browser starts database-backed graphs against one local development server.
  workers: 2,
  testDir: "./tests/e2e", reporter: [["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:3000", channel: "chromium", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: `${process.env.GIGBID_TEST_PYTHON ?? "uv run python"} -m scripts.test_server`,
      cwd: path.resolve(__dirname, "../.."), url: "http://127.0.0.1:8000/health/ready", reuseExistingServer: false },
    { command: "npm run dev", url: "http://127.0.0.1:3000", reuseExistingServer: false,
      env: { NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000", API_INTERNAL_URL: "http://127.0.0.1:8000" } },
  ],
});
