import { defineConfig, devices } from "@playwright/test";

// End-to-end smoke test of the built app under the dashboard's real Content-Security-Policy:
// the GitHub Pages demo (fake API) through a static server that sends the same CSP header, and
// the real dashboard app (scripts/e2e_dashboard.py) for signing in. Run `npm run build` and
// `uv run python scripts/build_demo.py site` (repo root) first; CI does.
const channel = process.env.PW_CHANNEL; // "chrome" locally if Playwright's Chromium isn't installed

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: { ...(channel ? { channel } : {}), trace: "retain-on-failure" },
  projects: [
    { name: "phone", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
    { name: "small-phone", use: { ...devices["Pixel 7"], viewport: { width: 360, height: 740 } } },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: [
    {
      command: "node e2e/serve.mjs ../site 4173",
      url: "http://127.0.0.1:4173/demo/",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "uv run --project .. python ../scripts/e2e_dashboard.py 4174",
      url: "http://127.0.0.1:4174/login",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
