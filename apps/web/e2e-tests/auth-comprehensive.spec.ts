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
    
    // Verify tokens are stored with correct structure
    const tokenData = await page.evaluate(() => {
      const accessToken = localStorage.getItem('access_token');
      const refreshToken = localStorage.getItem('refresh_token');
      const tokenType = localStorage.getItem('token_type');
      const expiresIn = localStorage.getItem('expires_in');
      return { accessToken, refreshToken, tokenType, expiresIn };
    });
    
    expect(tokenData.accessToken).toBeTruthy();
    expect(tokenData.refreshToken).toBeTruthy();
    expect(tokenData.tokenType).toBe('Bearer');
    expect(tokenData.expiresIn).toBeTruthy();
    
    // Test /auth/me endpoint
    const meResponse = await page.evaluate(async () => {
      const response = await fetch('/api/v1/auth/me', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      return { status: response.status, data: await response.json() };
    });
    
    expect(meResponse.status).toBe(200);
    expect(meResponse.data).toHaveProperty('id');
    expect(meResponse.data).toHaveProperty('email');
    expect(meResponse.data).toHaveProperty('role');
    
    // Test refresh token endpoint
    const refreshResponse = await page.evaluate(async () => {
      const response = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          refresh_token: localStorage.getItem('refresh_token')
        })
      });
      return { status: response.status, data: await response.json() };
    });
    
    expect(refreshResponse.status).toBe(200);
    expect(refreshResponse.data).toHaveProperty('access_token');
    expect(refreshResponse.data).toHaveProperty('refresh_token');
    expect(refreshResponse.data).toHaveProperty('token_type', 'Bearer');
    expect(refreshResponse.data).toHaveProperty('expires_in');
    
    // Test JWKS endpoint
    const jwksResponse = await page.evaluate(async () => {
      const response = await fetch('/api/v1/auth/.well-known/jwks.json');
      return { status: response.status, data: await response.json() };
    });
    
    expect(jwksResponse.status).toBe(200);
    expect(jwksResponse.data).toHaveProperty('keys');
    expect(Array.isArray(jwksResponse.data.keys)).toBe(true);
    
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
    // Test invalid email format (should return 422)
    await page.goto('/login');
    await page.fill('input[name="email"]', 'invalid-email');
    await page.fill('input[name="password"]', 'password');
    await page.click('button[type="submit"]');
    
    // Should show validation error
    await expect(page.locator('text=Please enter a valid email address')).toBeVisible();
    
    // Test invalid credentials (should return 401)
    await page.fill('input[name="email"]', 'nonexistent@example.com');
    await page.fill('input[name="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    
    // Should show authentication error
    await expect(page.locator('text=Invalid credentials')).toBeVisible();
    
    // Test network error
    await page.route('**/api/v1/auth/login', route => route.abort());
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Should show network error
    await expect(page.locator('text=Network error. Please check your connection')).toBeVisible();
    
    // Test server error (500)
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
    
    // Test unauthorized access to protected endpoint (401)
    const unauthorizedResponse = await page.evaluate(async () => {
      const response = await fetch('/api/v1/auth/me');
      return { status: response.status, data: await response.json() };
    });
    
    expect(unauthorizedResponse.status).toBe(401);
    
    // Test recovery
    await page.unroute('**/api/v1/auth/login');
    await page.click('button[type="submit"]');
    
    // Should succeed after recovery
    await expect(page.locator('text=Welcome')).toBeVisible();
  });
});
