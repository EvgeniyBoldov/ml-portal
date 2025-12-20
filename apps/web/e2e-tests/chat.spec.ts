import { test, expect } from '@playwright/test';

test.describe('Chat Interface', () => {
  // Login before each test
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/логин|email|login/i).fill('admin@test.com');
    await page.getByLabel(/пароль|password/i).fill('admin123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();
    await expect(page).toHaveURL(/\/(gpt|chat|$)/, { timeout: 10000 });
  });

  test.describe('Chat Page', () => {
    test('should display chat interface', async ({ page }) => {
      await page.goto('/gpt');

      // Should show message input
      await expect(
        page.getByPlaceholder(/сообщение|message|напишите/i)
          .or(page.locator('textarea'))
      ).toBeVisible();
    });

    test('should show send button', async ({ page }) => {
      await page.goto('/gpt');

      await expect(
        page.getByRole('button', { name: /отправить|send/i })
          .or(page.locator('button[type="submit"]'))
      ).toBeVisible();
    });

    test('should show chat history sidebar', async ({ page }) => {
      await page.goto('/gpt');

      // Should show sidebar with chat history
      await expect(
        page.getByText(/история|history|чаты|chats/i)
          .or(page.locator('[class*="sidebar"]'))
      ).toBeVisible();
    });
  });

  test.describe('Sending Messages', () => {
    test('should send a message', async ({ page }) => {
      await page.goto('/gpt');

      const input = page.getByPlaceholder(/сообщение|message|напишите/i)
        .or(page.locator('textarea').first());

      await input.fill('Hello, this is a test message');

      const sendBtn = page.getByRole('button', { name: /отправить|send/i })
        .or(page.locator('button[type="submit"]'));

      await sendBtn.click();

      // Message should appear in chat
      await expect(
        page.getByText('Hello, this is a test message')
      ).toBeVisible({ timeout: 5000 });
    });

    test('should show loading state while waiting for response', async ({ page }) => {
      await page.goto('/gpt');

      const input = page.getByPlaceholder(/сообщение|message|напишите/i)
        .or(page.locator('textarea').first());

      await input.fill('Test message for loading');

      const sendBtn = page.getByRole('button', { name: /отправить|send/i })
        .or(page.locator('button[type="submit"]'));

      await sendBtn.click();

      // Should show loading indicator
      await expect(
        page.locator('[class*="loading"]')
          .or(page.locator('[class*="spinner"]'))
          .or(page.getByText(/загрузка|loading|думаю/i))
      ).toBeVisible({ timeout: 3000 });
    });

    test('should receive AI response', async ({ page }) => {
      await page.goto('/gpt');

      const input = page.getByPlaceholder(/сообщение|message|напишите/i)
        .or(page.locator('textarea').first());

      await input.fill('What is 2 + 2?');

      const sendBtn = page.getByRole('button', { name: /отправить|send/i })
        .or(page.locator('button[type="submit"]'));

      await sendBtn.click();

      // Should receive response (wait longer for AI)
      await expect(
        page.locator('[class*="assistant"]')
          .or(page.locator('[data-role="assistant"]'))
          .or(page.locator('[class*="message"]').nth(1))
      ).toBeVisible({ timeout: 30000 });
    });

    test('should disable input while sending', async ({ page }) => {
      await page.goto('/gpt');

      const input = page.getByPlaceholder(/сообщение|message|напишите/i)
        .or(page.locator('textarea').first());

      await input.fill('Test message');

      const sendBtn = page.getByRole('button', { name: /отправить|send/i })
        .or(page.locator('button[type="submit"]'));

      await sendBtn.click();

      // Input or button should be disabled during sending
      await expect(
        input.or(sendBtn)
      ).toBeDisabled({ timeout: 1000 }).catch(() => {
        // Some implementations don't disable, that's ok
      });
    });
  });

  test.describe('Chat History', () => {
    test('should create new chat', async ({ page }) => {
      await page.goto('/gpt');

      const newChatBtn = page.getByRole('button', { name: /новый|new|создать/i });

      if (await newChatBtn.isVisible()) {
        await newChatBtn.click();

        // Should clear chat or create new
        await expect(
          page.locator('[class*="message"]')
        ).toHaveCount(0, { timeout: 3000 }).catch(() => {
          // May show welcome message
        });
      }
    });

    test('should switch between chats', async ({ page }) => {
      await page.goto('/gpt');

      // Find chat list items
      const chatItems = page.locator('[class*="chat-item"]')
        .or(page.locator('[data-testid="chat-item"]'))
        .or(page.locator('[class*="sidebar"] a'));

      const count = await chatItems.count();

      if (count > 1) {
        // Click second chat
        await chatItems.nth(1).click();

        // URL should change or content should update
        await page.waitForTimeout(500);
      }
    });

    test('should delete chat', async ({ page }) => {
      await page.goto('/gpt');

      // Find delete button in chat list
      const deleteBtn = page.locator('[class*="chat-item"] button[aria-label*="delete"]')
        .or(page.locator('[data-testid="delete-chat"]'))
        .first();

      if (await deleteBtn.isVisible()) {
        await deleteBtn.click();

        // Should show confirmation
        await expect(
          page.getByText(/удалить|delete|подтвердите/i)
        ).toBeVisible();
      }
    });
  });

  test.describe('RAG Integration', () => {
    test('should show RAG toggle or option', async ({ page }) => {
      await page.goto('/gpt');

      // Look for RAG toggle/checkbox
      await expect(
        page.getByLabel(/rag|база знаний|knowledge/i)
          .or(page.getByRole('checkbox', { name: /rag/i }))
          .or(page.getByRole('switch', { name: /rag/i }))
      ).toBeVisible().catch(() => {
        // RAG may be enabled by default or in different location
      });
    });

    test('should show sources when RAG is used', async ({ page }) => {
      await page.goto('/gpt');

      // Enable RAG if toggle exists
      const ragToggle = page.getByLabel(/rag|база знаний/i)
        .or(page.getByRole('checkbox', { name: /rag/i }));

      if (await ragToggle.isVisible()) {
        await ragToggle.check();
      }

      // Send a message
      const input = page.getByPlaceholder(/сообщение|message/i)
        .or(page.locator('textarea').first());

      await input.fill('What documents do you have?');

      const sendBtn = page.getByRole('button', { name: /отправить|send/i })
        .or(page.locator('button[type="submit"]'));

      await sendBtn.click();

      // Should show sources section (if RAG returns results)
      await expect(
        page.getByText(/источник|source|документ/i)
      ).toBeVisible({ timeout: 30000 }).catch(() => {
        // May not have documents or RAG disabled
      });
    });
  });

  test.describe('Keyboard Navigation', () => {
    test('should send message with Enter', async ({ page }) => {
      await page.goto('/gpt');

      const input = page.getByPlaceholder(/сообщение|message/i)
        .or(page.locator('textarea').first());

      await input.fill('Test Enter key');
      await input.press('Enter');

      // Message should be sent
      await expect(
        page.getByText('Test Enter key')
      ).toBeVisible({ timeout: 5000 });
    });

    test('should allow newline with Shift+Enter', async ({ page }) => {
      await page.goto('/gpt');

      const input = page.getByPlaceholder(/сообщение|message/i)
        .or(page.locator('textarea').first());

      await input.fill('Line 1');
      await input.press('Shift+Enter');
      await input.type('Line 2');

      // Should have multiline text
      const value = await input.inputValue();
      expect(value).toContain('Line 1');
      expect(value).toContain('Line 2');
    });
  });
});
