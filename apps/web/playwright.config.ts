import path from "node:path";

import { defineConfig, devices } from "@playwright/test";


const noProxy = [process.env.NO_PROXY, "127.0.0.1", "localhost"]
  .filter(Boolean)
  .join(",");
process.env.NO_PROXY = noProxy;
process.env.no_proxy = noProxy;

const repositoryRoot = path.resolve(__dirname, "../..");
const python = process.env.REFINEQ_PYTHON ?? "python";
const testDataRoot = path.join(__dirname, ".playwright-data");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  outputDir: "./test-results",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.CI ? {} : { channel: "chrome" as const }),
      },
    },
  ],
  webServer: [
    {
      command: `"${python}" -m uvicorn refineq.api.app:app --host 127.0.0.1 --port 8000`,
      cwd: repositoryRoot,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repositoryRoot, "src"),
        REFINEQ_DATA_ROOT: testDataRoot,
        REFINEQ_HOST: "127.0.0.1",
        REFINEQ_PORT: "8000",
        REFINEQ_PASSWORD_RESET_EXPOSE_TOKEN: "true",
      },
      url: "http://127.0.0.1:8000/health/live",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      cwd: __dirname,
      env: {
        ...process.env,
        REFINEQ_API_ORIGIN: "http://127.0.0.1:8000",
      },
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
