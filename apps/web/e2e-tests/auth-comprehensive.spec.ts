import { test, expect } from '@playwright/test';

test.describe('Comprehensive Authentication E2E Tests', () => {
  test('Complete User Journey: Registration → Email Verification → Login → Profile Update → Password Change → Logout', async ({ page }) => {
    // Step 1: Registration
    await page.goto('/register');
    await page.fill('input[name="email"]', `comprehensive_${Date.now()}@example.com`);
    await page.fill('input[name="password"]', 'ComprehensivePassword123!');
    await page.fill('input[name="confirmPassword"]', 'ComprehensivePassword123!');
    await page.fill('input[name="firstName"]', 'Test');
    await page.fill('input[name="lastName"]', 'User');
    await page.click('button[type="submit"]');
    
    // Verify registration success
    await expect(page.locator('text=Registration successful')).toBeVisible();
    await expect(page.locator('text=Please check your email for verification')).toBeVisible();
    
    // Step 2: Email verification (simulated)
    await page.goto('/verify-email?token=test-verification-token');
    await expect(page.locator('text=Email verified successfully')).toBeVisible();
    
    // Step 3: Login
    await page.goto('/login');
    await page.fill('input[name="email"]', `comprehensive_${Date.now()}@example.com`);
    await page.fill('input[name="password"]', 'ComprehensivePassword123!');
    await page.click('button[type="submit"]');
    
    // Verify login success
    await expect(page.locator('text=Welcome, Test User')).toBeVisible();
    
    // Step 4: Profile update
    await page.click('text=Profile');
    await page.fill('input[name="firstName"]', 'Updated');
    await page.fill('input[name="lastName"]', 'Name');
    await page.fill('input[name="bio"]', 'This is my updated bio');
    await page.click('button[type="submit"]');
    
    // Verify profile update
    await expect(page.locator('text=Profile updated successfully')).toBeVisible();
    await expect(page.locator('text=Welcome, Updated Name')).toBeVisible();
    
    // Step 5: Password change
    await page.click('text=Security');
    await page.fill('input[name="currentPassword"]', 'ComprehensivePassword123!');
    await page.fill('input[name="newPassword"]', 'NewComprehensivePassword123!');
    await page.fill('input[name="confirmNewPassword"]', 'NewComprehensivePassword123!');
    await page.click('button[type="submit"]');
    
    // Verify password change
    await expect(page.locator('text=Password changed successfully')).toBeVisible();
    
    // Step 6: Logout
    await page.click('text=Logout');
    await expect(page.locator('text=Login')).toBeVisible();
    
    // Verify logout by trying to access protected page
    await page.goto('/dashboard');
    await expect(page.locator('text=Please login to continue')).toBeVisible();
  });

  test('Advanced Token Management: Access Token → Refresh Token → Token Expiry → Auto Refresh', async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Verify tokens are stored
    const accessToken = await page.evaluate(() => localStorage.getItem('access_token'));
    const refreshToken = await page.evaluate(() => localStorage.getItem('refresh_token'));
    expect(accessToken).toBeTruthy();
    expect(refreshToken).toBeTruthy();
    
    // Simulate token expiry
    await page.evaluate(() => {
      localStorage.setItem('access_token', 'expired-token');
    });
    
    // Make API call that should trigger refresh
    await page.evaluate(async () => {
      const response = await fetch('/api/v1/users/me', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      return response.status;
    });
    
    // Verify new token is stored
    const newAccessToken = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(newAccessToken).not.toBe('expired-token');
    
    // Verify user is still authenticated
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Security Features: Rate Limiting → Account Lockout → Password Strength → 2FA', async ({ page }) => {
    // Test rate limiting
    await page.goto('/login');
    
    // Try multiple failed logins
    for (let i = 0; i < 5; i++) {
      await page.fill('input[name="email"]', 'test@example.com');
      await page.fill('input[name="password"]', 'WrongPassword');
      await page.click('button[type="submit"]');
      
      if (i < 4) {
        await expect(page.locator('text=Invalid credentials')).toBeVisible();
      }
    }
    
    // Should show rate limiting message
    await expect(page.locator('text=Too many failed attempts')).toBeVisible();
    await expect(page.locator('text=Please try again in')).toBeVisible();
    
    // Test password strength validation
    await page.goto('/register');
    await page.fill('input[name="email"]', 'strength@example.com');
    await page.fill('input[name="password"]', 'weak');
    await page.fill('input[name="confirmPassword"]', 'weak');
    
    // Should show password strength requirements
    await expect(page.locator('text=Password must be at least 8 characters')).toBeVisible();
    await expect(page.locator('text=Password must contain uppercase letter')).toBeVisible();
    await expect(page.locator('text=Password must contain number')).toBeVisible();
    
    // Test 2FA setup
    await page.fill('input[name="password"]', 'StrongPassword123!');
    await page.fill('input[name="confirmPassword"]', 'StrongPassword123!');
    await page.click('button[type="submit"]');
    
    // Should prompt for 2FA setup
    await expect(page.locator('text=Enable Two-Factor Authentication')).toBeVisible();
    
    // Skip 2FA for this test
    await page.click('text=Skip for now');
  });

  test('Error Handling: Invalid Input → Network Errors → Server Errors → Recovery', async ({ page }) => {
    // Test invalid email format
    await page.goto('/login');
    await page.fill('input[name="email"]', 'invalid-email');
    await page.fill('input[name="password"]', 'password');
    await page.click('button[type="submit"]');
    
    // Should show validation error
    await expect(page.locator('text=Please enter a valid email address')).toBeVisible();
    
    // Test network error
    await page.route('**/api/v1/auth/login', route => route.abort());
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Should show network error
    await expect(page.locator('text=Network error. Please check your connection')).toBeVisible();
    
    // Test server error
    await page.unroute('**/api/v1/auth/login');
    await page.route('**/api/v1/auth/login', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal server error' })
      });
    });
    
    await page.click('button[type="submit"]');
    
    // Should show server error
    await expect(page.locator('text=Server error. Please try again later')).toBeVisible();
    
    // Test recovery
    await page.unroute('**/api/v1/auth/login');
    await page.click('button[type="submit"]');
    
    // Should succeed after recovery
    await expect(page.locator('text=Welcome')).toBeVisible();
  });
});
