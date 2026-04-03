import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 180000,
  expect: {
    timeout: 30000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    channel: "msedge",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "poetry run uvicorn backend_service.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/health",
      cwd: "..",
      reuseExistingServer: true,
      timeout: 180000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      cwd: ".",
      reuseExistingServer: true,
      timeout: 180000,
      env: {
        VITE_API_BASE_URL: "http://127.0.0.1:8000",
      },
    },
  ],
});
