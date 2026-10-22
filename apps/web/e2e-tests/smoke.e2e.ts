import { expect, test } from '@playwright/test';

test('unauthenticated chat visit redirects to the login form', async ({ page }) => {
  await page.route('**/auth/me', route =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Not authenticated"}' })
  );
  await page.route('**/auth/refresh', route =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Invalid refresh token"}' })
  );

  await page.goto('/gpt/chat');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Добро пожаловать' })).toBeVisible();
  await expect(page.getByPlaceholder('Введите логин')).toBeVisible();
});
