import { test, expect } from '@playwright/test';

test.describe('Authentication E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the application
    await page.goto('/');
  });

  test('Complete Auth Flow: Registration → Login → Usage → Logout', async ({ page }) => {
    // Step 1: Registration
    await page.click('text=Sign Up');
    await page.fill('input[name="email"]', `test_${Date.now()}@example.com`);
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.fill('input[name="confirmPassword"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Wait for registration success
    await expect(page.locator('text=Registration successful')).toBeVisible();
    
    // Step 2: Login
    await page.fill('input[name="email"]', `test_${Date.now()}@example.com`);
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Wait for login success
    await expect(page.locator('text=Welcome')).toBeVisible();
    
    // Step 3: Usage - Navigate to dashboard
    await page.click('text=Dashboard');
    await expect(page.locator('text=Dashboard')).toBeVisible();
    
    // Step 4: Logout
    await page.click('text=Logout');
    await expect(page.locator('text=Login')).toBeVisible();
  });

  test('Refresh Token Flow', async ({ page }) => {
    // Login first
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Wait for login
    await expect(page.locator('text=Welcome')).toBeVisible();
    
    // Simulate token refresh by making API calls
    await page.evaluate(async () => {
      // Make multiple API calls to trigger token refresh
      for (let i = 0; i < 5; i++) {
        await fetch('/api/v1/users/me', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        });
      }
    });
    
    // Verify user is still authenticated
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Password Change Flow', async ({ page }) => {
    // Login first
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Navigate to profile
    await page.click('text=Profile');
    
    // Change password
    await page.fill('input[name="currentPassword"]', 'TestPassword123!');
    await page.fill('input[name="newPassword"]', 'NewPassword123!');
    await page.fill('input[name="confirmNewPassword"]', 'NewPassword123!');
    await page.click('button[type="submit"]');
    
    // Verify password change success
    await expect(page.locator('text=Password changed successfully')).toBeVisible();
  });

  test('Account Deactivation', async ({ page }) => {
    // Login first
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Navigate to profile
    await page.click('text=Profile');
    
    // Deactivate account
    await page.click('text=Deactivate Account');
    await page.click('button:has-text("Confirm")');
    
    // Verify account deactivation
    await expect(page.locator('text=Account deactivated')).toBeVisible();
    
    // Try to login with deactivated account
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Should show error
    await expect(page.locator('text=Account is deactivated')).toBeVisible();
  });
});
