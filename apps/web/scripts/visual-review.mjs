import fs from 'node:fs/promises';
import path from 'node:path';
import { lookup } from 'node:dns/promises';
import { chromium } from 'playwright';

const targetUrl = process.argv[2] || 'http://nginx:8080/gpt/collections';
const label = (process.argv[3] || new URL(targetUrl).pathname.split('/').filter(Boolean).join('-') || 'page')
  .replace(/[^a-zA-Z0-9_-]+/g, '-')
  .replace(/^-+|-+$/g, '')
  .slice(0, 80) || 'page';
const outputDir = path.resolve('test-results/visual-review');
const retentionMs = 7 * 24 * 60 * 60 * 1000;
const maxScreenshots = 20;

await fs.mkdir(outputDir, { recursive: true });

const existing = (await fs.readdir(outputDir, { withFileTypes: true }))
  .filter(entry => entry.isFile() && entry.name.endsWith('.png'));
const screenshots = await Promise.all(existing.map(async entry => {
  const filePath = path.join(outputDir, entry.name);
  const stat = await fs.stat(filePath);
  return { filePath, mtimeMs: stat.mtimeMs };
}));
const cutoff = Date.now() - retentionMs;
await Promise.all(screenshots.filter(file => file.mtimeMs < cutoff).map(file => fs.rm(file.filePath)));
const retained = screenshots.filter(file => file.mtimeMs >= cutoff).sort((a, b) => b.mtimeMs - a.mtimeMs);
await Promise.all(retained.slice(maxScreenshots - 1).map(file => fs.rm(file.filePath)));

const timestamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '').replace('T', '-').replace('Z', 'Z');
const screenshotPath = path.join(outputDir, `${timestamp}-${label}.png`);
const { address: chromiumAddress } = await lookup('chromium-review', { family: 4 });
const browser = await chromium.connectOverCDP(`http://${chromiumAddress}:9222`);
const context = browser.contexts()[0];
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));

try {
  const response = await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(JSON.stringify({
    url: page.url(),
    title: await page.title(),
    httpStatus: response?.status() ?? null,
    screenshot: screenshotPath,
    pageErrors,
    bodyText: (await page.locator('body').innerText()).slice(0, 5000),
  }, null, 2));
} finally {
  await page.close();
  await browser.close();
}
