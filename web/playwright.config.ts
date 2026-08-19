import {defineConfig, devices} from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {baseURL: "http://127.0.0.1:4173", trace: "on-first-retry"},
  webServer: {command: "pnpm preview --host 127.0.0.1", port: 4173, reuseExistingServer: !process.env.CI},
  projects: [
    {name: "desktop", use: {...devices["Desktop Chrome"]}},
    {name: "mobile", use: {...devices["iPhone 13"]}},
  ],
});

