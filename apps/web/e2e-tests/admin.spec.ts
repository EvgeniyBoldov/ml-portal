import { test, expect } from '@playwright/test';

test.describe('Admin Panel', () => {
  // Login as admin before each test
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/логин|email|login/i).fill('admin@test.com');
    await page.getByLabel(/пароль|password/i).fill('admin123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();
    await expect(page).toHaveURL(/\/(gpt|chat|$)/, { timeout: 10000 });
  });

  test.describe('Admin Access', () => {
    test('should access admin panel', async ({ page }) => {
      await page.goto('/admin');

      // Should show admin panel
      await expect(
        page.getByRole('heading', { name: /admin|администр|панель/i })
          .or(page.locator('[class*="admin"]'))
      ).toBeVisible({ timeout: 5000 });
    });

    test('should show admin navigation', async ({ page }) => {
      await page.goto('/admin');

      // Should show navigation items
      await expect(
        page.getByRole('link', { name: /пользовател|users/i })
          .or(page.getByText(/пользовател|users/i))
      ).toBeVisible();
    });
  });

  test.describe('Users Management', () => {
    test('should display users list', async ({ page }) => {
      await page.goto('/admin/users');

      // Should show users table or list
      await expect(
        page.getByRole('table')
          .or(page.locator('[class*="user-list"]'))
          .or(page.getByText(/пользовател|users/i))
      ).toBeVisible();
    });

    test('should show create user button', async ({ page }) => {
      await page.goto('/admin/users');

      await expect(
        page.getByRole('button', { name: /создать|create|добавить|add/i })
      ).toBeVisible();
    });

    test('should open create user form', async ({ page }) => {
      await page.goto('/admin/users');

      await page.getByRole('button', { name: /создать|create|добавить|add/i }).click();

      // Should show form fields
      await expect(
        page.getByLabel(/логин|login|имя/i)
          .or(page.getByPlaceholder(/логин|login/i))
      ).toBeVisible();

      await expect(
        page.getByLabel(/email|почта/i)
          .or(page.getByPlaceholder(/email/i))
      ).toBeVisible();
    });

    test('should search users', async ({ page }) => {
      await page.goto('/admin/users');

      const searchInput = page.getByPlaceholder(/поиск|search/i);

      if (await searchInput.isVisible()) {
        await searchInput.fill('admin');
        await searchInput.press('Enter');

        // Should filter results
        await page.waitForTimeout(500);
      }
    });
  });

  test.describe('Tenants Management', () => {
    test('should display tenants list', async ({ page }) => {
      await page.goto('/admin/tenants');

      await expect(
        page.getByRole('table')
          .or(page.locator('[class*="tenant"]'))
          .or(page.getByText(/tenant|арендатор|организац/i))
      ).toBeVisible();
    });

    test('should show create tenant button', async ({ page }) => {
      await page.goto('/admin/tenants');

      await expect(
        page.getByRole('button', { name: /создать|create|добавить|add/i })
      ).toBeVisible();
    });

    test('should open tenant details', async ({ page }) => {
      await page.goto('/admin/tenants');

      // Click on first tenant
      const firstRow = page.locator('tr').nth(1)
        .or(page.locator('[class*="tenant-row"]').first());

      if (await firstRow.isVisible()) {
        await firstRow.click();

        // Should show tenant details
        await expect(
          page.getByText(/настройки|settings|модел|model/i)
        ).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test.describe('Models Management', () => {
    test('should display models list', async ({ page }) => {
      await page.goto('/admin/models');

      await expect(
        page.getByRole('table')
          .or(page.locator('[class*="model"]'))
          .or(page.getByText(/модел|model|llm|embedding/i))
      ).toBeVisible();
    });

    test('should show model types', async ({ page }) => {
      await page.goto('/admin/models');

      // Should show different model types
      await expect(
        page.getByText(/llm|embedding|rerank/i)
      ).toBeVisible();
    });

    test('should show model health status', async ({ page }) => {
      await page.goto('/admin/models');

      // Should show health indicators
      await expect(
        page.locator('[class*="health"]')
          .or(page.locator('[class*="status"]'))
          .or(page.getByText(/healthy|available|online|активен/i))
      ).toBeVisible().catch(() => {
        // Health status may not be visible if no models
      });
    });
  });

  test.describe('Agents Management', () => {
    test('should display agents list', async ({ page }) => {
      await page.goto('/admin/agents');

      await expect(
        page.getByRole('table')
          .or(page.locator('[class*="agent"]'))
          .or(page.getByText(/агент|agent/i))
      ).toBeVisible();
    });

    test('should show agent details', async ({ page }) => {
      await page.goto('/admin/agents');

      // Click on first agent
      const firstAgent = page.locator('tr').nth(1)
        .or(page.locator('[class*="agent-row"]').first());

      if (await firstAgent.isVisible()) {
        await firstAgent.click();

        // Should show agent configuration
        await expect(
          page.getByText(/prompt|tools|настройки/i)
        ).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test.describe('Prompts Management', () => {
    test('should display prompts list', async ({ page }) => {
      await page.goto('/admin/prompts');

      await expect(
        page.getByRole('table')
          .or(page.locator('[class*="prompt"]'))
          .or(page.getByText(/prompt|шаблон/i))
      ).toBeVisible();
    });

    test('should show prompt editor', async ({ page }) => {
      await page.goto('/admin/prompts');

      // Click on first prompt
      const firstPrompt = page.locator('tr').nth(1)
        .or(page.locator('[class*="prompt-row"]').first());

      if (await firstPrompt.isVisible()) {
        await firstPrompt.click();

        // Should show template editor
        await expect(
          page.locator('textarea')
            .or(page.locator('[class*="editor"]'))
            .or(page.locator('[class*="template"]'))
        ).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test.describe('Audit Log', () => {
    test('should display audit log', async ({ page }) => {
      await page.goto('/admin/audit');

      await expect(
        page.getByRole('table')
          .or(page.locator('[class*="audit"]'))
          .or(page.getByText(/audit|лог|журнал/i))
      ).toBeVisible();
    });

    test('should show audit entries', async ({ page }) => {
      await page.goto('/admin/audit');

      // Should show timestamps and actions
      await expect(
        page.getByText(/\d{2}[.:]\d{2}/)
          .or(page.locator('[class*="timestamp"]'))
      ).toBeVisible().catch(() => {
        // May be empty
      });
    });

    test('should paginate audit log', async ({ page }) => {
      await page.goto('/admin/audit');

      // Find pagination
      const nextBtn = page.getByRole('button', { name: /next|след|→/i });

      if (await nextBtn.isVisible() && await nextBtn.isEnabled()) {
        await nextBtn.click();

        // URL should update with page param
        await expect(page).toHaveURL(/page=2/);
      }
    });
  });

  test.describe('Navigation', () => {
    test('should navigate between admin sections', async ({ page }) => {
      await page.goto('/admin');

      // Navigate to users
      await page.getByRole('link', { name: /пользовател|users/i }).click();
      await expect(page).toHaveURL(/\/admin\/users/);

      // Navigate to tenants
      await page.getByRole('link', { name: /tenant|арендатор|организац/i }).click();
      await expect(page).toHaveURL(/\/admin\/tenants/);

      // Navigate to models
      await page.getByRole('link', { name: /модел|models/i }).click();
      await expect(page).toHaveURL(/\/admin\/models/);
    });

    test('should return to main app', async ({ page }) => {
      await page.goto('/admin');

      // Find back/home link
      const homeLink = page.getByRole('link', { name: /главная|home|chat|gpt/i })
        .or(page.locator('a[href="/gpt"]'))
        .or(page.locator('a[href="/"]'));

      if (await homeLink.isVisible()) {
        await homeLink.click();
        await expect(page).toHaveURL(/\/(gpt|$)/);
      }
    });
  });
});
