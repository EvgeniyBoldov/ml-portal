import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test.describe('Login Page', () => {
    test('should display login form', async ({ page }) => {
      await page.goto('/login');

      await expect(page.getByRole('heading', { name: /вход|login/i })).toBeVisible();
      await expect(page.getByLabel(/логин|email|login/i)).toBeVisible();
      await expect(page.getByLabel(/пароль|password/i)).toBeVisible();
      await expect(page.getByRole('button', { name: /войти|sign in|login/i })).toBeVisible();
    });

    test('should show validation error for empty fields', async ({ page }) => {
      await page.goto('/login');

      await page.getByRole('button', { name: /войти|sign in|login/i }).click();

      // Should show validation errors
      await expect(page.getByText(/обязательно|required/i)).toBeVisible();
    });

    test('should show error for invalid credentials', async ({ page }) => {
      await page.goto('/login');

      await page.getByLabel(/логин|email|login/i).fill('invalid@test.com');
      await page.getByLabel(/пароль|password/i).fill('wrongpassword');
      await page.getByRole('button', { name: /войти|sign in|login/i }).click();

      // Should show error message
      await expect(
        page.getByText(/неверный|invalid|ошибка|error/i)
      ).toBeVisible({ timeout: 10000 });
    });

    test('should redirect to main page after successful login', async ({ page }) => {
      await page.goto('/login');

      // Use test credentials (should be configured in test environment)
      await page.getByLabel(/логин|email|login/i).fill('admin@test.com');
      await page.getByLabel(/пароль|password/i).fill('admin123');
      await page.getByRole('button', { name: /войти|sign in|login/i }).click();

      // Should redirect to main page
      await expect(page).toHaveURL(/\/(gpt|chat|$)/, { timeout: 10000 });
    });
  });

  test.describe('Protected Routes', () => {
    test('should redirect to login when not authenticated', async ({ page }) => {
      await page.goto('/gpt');

      // Should redirect to login
      await expect(page).toHaveURL(/\/login/);
    });

    test('should redirect to login when accessing admin', async ({ page }) => {
      await page.goto('/admin');

      // Should redirect to login
      await expect(page).toHaveURL(/\/login/);
    });
  });

  test.describe('Logout', () => {
    test.beforeEach(async ({ page }) => {
      // Login first
      await page.goto('/login');
      await page.getByLabel(/логин|email|login/i).fill('admin@test.com');
      await page.getByLabel(/пароль|password/i).fill('admin123');
      await page.getByRole('button', { name: /войти|sign in|login/i }).click();
      await expect(page).toHaveURL(/\/(gpt|chat|$)/, { timeout: 10000 });
    });

    test('should logout and redirect to login', async ({ page }) => {
      // Find and click logout button
      await page.getByRole('button', { name: /выход|logout|выйти/i }).click();

      // Should redirect to login
      await expect(page).toHaveURL(/\/login/);
    });
  });
});
