const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.cjs', fullyParallel: false, workers: 1, retries: 0,
  timeout: 20000,
  use: {
    baseURL: 'http://127.0.0.1:47632', headless: true,
    viewport: { width: 1200, height: 900 }, timezoneId: 'America/New_York',
    screenshot: 'only-on-failure', trace: 'retain-on-failure'
  },
  webServer: { command: 'node scripts/serve.mjs', env: { PORT: '47632' }, url: 'http://127.0.0.1:47632', reuseExistingServer: false },
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]]
});
