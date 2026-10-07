import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:18841", trace: "retain-on-failure" },
  webServer: {
    command:
      "cd .. && COS_MODE=demo COS_DB_PATH=/private/tmp/chief-playwright.sqlite3 .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 18841",
    url: "http://127.0.0.1:18841/health",
    reuseExistingServer: false,
  },
});
