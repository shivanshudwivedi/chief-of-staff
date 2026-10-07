import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
const testData = mkdtempSync(join(tmpdir(), "chief-browser-"));
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:18841", trace: "retain-on-failure" },
  webServer: {
    command: "uv run uvicorn backend.app:app --host 127.0.0.1 --port 18841",
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    env: {
      COS_MODE: "demo",
      COS_DB_PATH: join(testData, "chief.sqlite3"),
      COS_MCP_CONFIG: "",
      COS_API_TOKEN: "",
      COS_BRIDGE_TOKEN: "",
      COS_IMESSAGE_ENABLED: "false",
    },
    url: "http://127.0.0.1:18841/health",
    reuseExistingServer: false,
  },
});
