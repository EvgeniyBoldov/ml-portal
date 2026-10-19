import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-tests',
  testMatch: ['chat-contract.e2e.ts', 'chat-attachments.e2e.ts'],
  timeout: 45_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [['list']],
  outputDir:
    process.env.CHAT_E2E_LIVE === '1'
      ? '/tmp/chat-live-e2e-results'
      : '/tmp/chat-contract-e2e-results',
  use: {
    baseURL: process.env.BASE_URL || 'http://nginx:8081',
    browserName: 'chromium',
    launchOptions: process.env.CHROMIUM_EXECUTABLE
      ? {
          executablePath: process.env.CHROMIUM_EXECUTABLE,
          args: ['--no-sandbox', '--disable-dev-shm-usage'],
        }
      : {},
    screenshot: 'only-on-failure',
  },
});
