import { test as base, expect, type Page, type TestType } from '@playwright/test';

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
type MyFixtures = {
  authenticatedPage: Page;
  adminPage: Page;
};

export const test = base.extend<MyFixtures>({
  // Page authenticated as default user (admin)
  authenticatedPage: async ({ page }, use: (page: Page) => Promise<void>) => {
    await login(page, testUsers.admin);
    await use(page);
  },

  // Page authenticated as admin (explicit)
  adminPage: async ({ page }, use: (page: Page) => Promise<void>) => {
    await login(page, testUsers.admin);
    await use(page);
  },
});

/**
 * Login helper function
 */
export async function login(
  page: Page,
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
  page: Page
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
  page: Page,
  urlPattern: string | RegExp
): Promise<void> {
  await page.waitForResponse(
    (response: any) => {
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
  page: Page,
  fileName: string,
  content: string,
  mimeType = 'text/plain'
): Promise<void> {
  const fileInput = page.locator('input[type="file"]');

  // Use TextEncoder instead of Buffer for browser compatibility
  const encoder = new TextEncoder();
  const uint8Array = encoder.encode(content);

  await fileInput.setInputFiles({
    name: fileName,
    mimeType,
    buffer: uint8Array,
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
  page: Page,
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
  page: Page
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
  page: Page
): Promise<number> {
  const rows = page.locator('tbody tr');
  return await rows.count();
}

/**
 * Select option from dropdown
 */
export async function selectOption(
  page: Page,
  label: string | RegExp,
  value: string
): Promise<void> {
  const select = page.getByLabel(label).or(page.getByRole('combobox', { name: label }));

  await select.click();
  await page.getByRole('option', { name: value }).click();
}

/**
 * Runtime refactor specific test data
 */
export const runtimeTestData = {
  simpleChat: {
    messages: [
      { role: 'user', content: 'Hello, how are you?' }
    ],
    expectedTools: [],
    expectedSteps: 1
  },
  toolExecution: {
    messages: [
      { role: 'user', content: 'Search for information about AI' }
    ],
    expectedTools: ['rag.search'],
    expectedSteps: 2
  },
  multiTool: {
    messages: [
      { role: 'user', content: 'Search for AI and then machine learning' }
    ],
    expectedTools: ['rag.search'],
    expectedSteps: 3
  },
  errorScenario: {
    messages: [
      { role: 'user', content: 'This should cause an error' }
    ],
    expectedTools: [],
    expectedSteps: 1,
    shouldError: true
  }
};

/**
 * Send chat message helper
 */
export async function sendChatMessage(
  page: Page,
  message: string
): Promise<void> {
  const messageInput = page.getByPlaceholder(/сообщение|message|напишите/i)
    .or(page.locator('textarea').first());
  
  await messageInput.fill(message);
  await page.getByRole('button', { name: /отправить|send/i }).click();
}

/**
 * Wait for assistant response
 */
export async function waitForAssistantResponse(
  page: Page,
  timeout = 30000
): Promise<void> {
  await expect(page.locator('.message.assistant').last()).toBeVisible({ timeout });
}

/**
 * Check for tool execution indicator
 */
export async function checkToolExecution(
  page: Page
): Promise<boolean> {
  const toolIndicator = page.locator('[class*="tool"], [data-testid*="tool"], .tool-call');
  return await toolIndicator.isVisible({ timeout: 5000 }).catch(() => false);
}

/**
 * Get current chat messages
 */
export async function getChatMessages(
  page: Page
): Promise<string[]> {
  const messages = page.locator('.message');
  const count = await messages.count();
  const texts: string[] = [];
  
  for (let i = 0; i < count; i++) {
    const text = await messages.nth(i).textContent();
    if (text) {
      texts.push(text.trim());
    }
  }
  
  return texts;
}

/**
 * Check for error message
 */
export async function checkForError(
  page: Page
): Promise<boolean> {
  const errorElement = page.locator('[class*="error"], [data-testid*="error"], .error-message');
  return await errorElement.isVisible({ timeout: 5000 }).catch(() => false);
}

/**
 * Wait for loading indicator to disappear
 */
export async function waitForLoadingComplete(
  page: Page
): Promise<void> {
  const loadingIndicator = page.locator('[class*="loading"], [class*="thinking"], .spinner');
  
  if (await loadingIndicator.isVisible({ timeout: 1000 })) {
    await expect(loadingIndicator).not.toBeVisible({ timeout: 30000 });
  }
}

// Re-export expect for convenience
export { expect };
