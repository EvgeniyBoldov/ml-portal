import { test as base, expect } from '@playwright/test';

/**
 * Test fixtures for e2e tests
 * Provides authenticated page and common utilities
 */

export interface TestUser {
  login: string;
  password: string;
  role: 'admin' | 'editor' | 'reader';
}

// Test users (should match test environment seed data)
export const testUsers: Record<string, TestUser> = {
  admin: {
    login: 'admin@test.com',
    password: 'admin123',
    role: 'admin',
  },
  editor: {
    login: 'editor@test.com',
    password: 'editor123',
    role: 'editor',
  },
  reader: {
    login: 'reader@test.com',
    password: 'reader123',
    role: 'reader',
  },
};

// Extended test with authenticated page
export const test = base.extend<{
  authenticatedPage: ReturnType<typeof base['page']>;
  adminPage: ReturnType<typeof base['page']>;
}>({
  // Page authenticated as default user (admin)
  authenticatedPage: async ({ page }, use) => {
    await login(page, testUsers.admin);
    await use(page);
  },

  // Page authenticated as admin (explicit)
  adminPage: async ({ page }, use) => {
    await login(page, testUsers.admin);
    await use(page);
  },
});

/**
 * Login helper function
 */
export async function login(
  page: ReturnType<typeof base['page']>,
  user: TestUser
): Promise<void> {
  await page.goto('/login');

  // Fill login form
  await page.getByLabel(/логин|email|login/i).fill(user.login);
  await page.getByLabel(/пароль|password/i).fill(user.password);
  await page.getByRole('button', { name: /войти|sign in|login/i }).click();

  // Wait for redirect
  await expect(page).toHaveURL(/\/(gpt|chat|admin|$)/, { timeout: 10000 });
}

/**
 * Logout helper function
 */
export async function logout(
  page: ReturnType<typeof base['page']>
): Promise<void> {
  // Try to find and click logout button
  const logoutBtn = page.getByRole('button', { name: /выход|logout|выйти/i });

  if (await logoutBtn.isVisible()) {
    await logoutBtn.click();
    await expect(page).toHaveURL(/\/login/);
  }
}

/**
 * Wait for API response
 */
export async function waitForApi(
  page: ReturnType<typeof base['page']>,
  urlPattern: string | RegExp
): Promise<void> {
  await page.waitForResponse(
    response => {
      const url = response.url();
      if (typeof urlPattern === 'string') {
        return url.includes(urlPattern);
      }
      return urlPattern.test(url);
    },
    { timeout: 30000 }
  );
}

/**
 * Upload file helper
 */
export async function uploadFile(
  page: ReturnType<typeof base['page']>,
  fileName: string,
  content: string,
  mimeType = 'text/plain'
): Promise<void> {
  const fileInput = page.locator('input[type="file"]');

  await fileInput.setInputFiles({
    name: fileName,
    mimeType,
    buffer: Buffer.from(content),
  });
}

/**
 * Create test document content
 */
export function createTestDocument(lines = 100): string {
  const paragraphs = [];
  for (let i = 0; i < lines; i++) {
    paragraphs.push(
      `Paragraph ${i + 1}: This is test content for RAG document testing. ` +
        `It contains various words and phrases that can be used for search testing. ` +
        `Keywords: test, document, rag, search, embedding, vector.`
    );
  }
  return paragraphs.join('\n\n');
}

/**
 * Wait for toast notification
 */
export async function waitForToast(
  page: ReturnType<typeof base['page']>,
  textPattern: string | RegExp
): Promise<void> {
  await expect(
    page.locator('[class*="toast"]').or(page.locator('[role="alert"]'))
  ).toContainText(textPattern, { timeout: 10000 });
}

/**
 * Close modal if open
 */
export async function closeModal(
  page: ReturnType<typeof base['page']>
): Promise<void> {
  const closeBtn = page
    .getByRole('button', { name: /close|закрыть|×/i })
    .or(page.locator('[aria-label="Close"]'));

  if (await closeBtn.isVisible()) {
    await closeBtn.click();
  } else {
    // Try pressing Escape
    await page.keyboard.press('Escape');
  }
}

/**
 * Get table row count
 */
export async function getTableRowCount(
  page: ReturnType<typeof base['page']>
): Promise<number> {
  const rows = page.locator('tbody tr');
  return await rows.count();
}

/**
 * Select option from dropdown
 */
export async function selectOption(
  page: ReturnType<typeof base['page']>,
  label: string | RegExp,
  value: string
): Promise<void> {
  const select = page.getByLabel(label).or(page.getByRole('combobox', { name: label }));

  await select.click();
  await page.getByRole('option', { name: value }).click();
}

// Re-export expect for convenience
export { expect };
