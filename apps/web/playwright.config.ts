import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
export default defineConfig({
  // Each browser starts database-backed graphs against one local development server.
  workers: 2,
  testDir: "./tests/e2e", reporter: [["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:3002", channel: "chromium", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: `${process.env.GIGBID_TEST_PYTHON ?? "uv run python"} -m uvicorn simulator.app:app --host 127.0.0.1 --port 8086`, cwd: path.resolve(__dirname, "../.."), url: "http://127.0.0.1:8086/health", reuseExistingServer: false,
      env: { STUDENT_SIM_API_KEY: "browser_sim_only", STUDENT_SIM_DATABASE: "work/browser-student-sim.sqlite", STUDENT_SIM_ALLOW_FAULTS: "1", STUDENT_SIM_CATALOGUE: "synthetic" } },
    { command: `${process.env.GIGBID_TEST_PYTHON ?? "uv run python"} -m scripts.test_server`,
      cwd: path.resolve(__dirname, "../.."), url: "http://127.0.0.1:8002/health/ready", reuseExistingServer: false },
    { command: "npm run dev -- --port 3002", url: "http://127.0.0.1:3002", reuseExistingServer: false,
      env: { NEXT_PUBLIC_API_URL: "http://127.0.0.1:8002", API_INTERNAL_URL: "http://127.0.0.1:8002", GIGBID_TEST_DIST: ".next-e2e" } },
  ],
});
