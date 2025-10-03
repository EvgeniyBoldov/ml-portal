import { test, expect } from '@playwright/test';

test.describe('Basic E2E Tests', () => {
  test('should load the application', async ({ page }) => {
    await page.goto('/');
    
    // Check if the page loads without errors
    await expect(page).toHaveTitle(/ML Portal/);
    
    // Check if main elements are present
    await expect(page.locator('body')).toBeVisible();
  });

  test('should have proper meta tags', async ({ page }) => {
    await page.goto('/');
    
    // Check for essential meta tags
    const viewport = page.locator('meta[name="viewport"]');
    await expect(viewport).toHaveAttribute('content', /width=device-width/);
  });

  test('should be responsive', async ({ page }) => {
    await page.goto('/');
    
    // Test mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await expect(page.locator('body')).toBeVisible();
    
    // Test desktop viewport
    await page.setViewportSize({ width: 1920, height: 1080 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('should handle navigation', async ({ page }) => {
    await page.goto('/');
    
    // Test that navigation doesn't cause errors
    await page.reload();
    await expect(page.locator('body')).toBeVisible();
  });
});
