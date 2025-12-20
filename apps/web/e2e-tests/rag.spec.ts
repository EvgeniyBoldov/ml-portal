import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('RAG Document Management', () => {
  // Login before each test
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/логин|email|login/i).fill('admin@test.com');
    await page.getByLabel(/пароль|password/i).fill('admin123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();
    await expect(page).toHaveURL(/\/(gpt|chat|rag|$)/, { timeout: 10000 });
  });

  test.describe('Document List', () => {
    test('should display document list page', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Should show RAG page elements
      await expect(page.getByRole('heading', { name: /документ|document|rag|база знаний/i })).toBeVisible();
    });

    test('should show upload button', async ({ page }) => {
      await page.goto('/gpt/rag');

      await expect(
        page.getByRole('button', { name: /загрузить|upload|добавить/i })
      ).toBeVisible();
    });

    test('should filter documents by status', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Find status filter
      const statusFilter = page.getByRole('combobox', { name: /статус|status/i });
      if (await statusFilter.isVisible()) {
        await statusFilter.click();
        await page.getByRole('option', { name: /ready|готов/i }).click();

        // URL should update with status param
        await expect(page).toHaveURL(/status=ready/);
      }
    });

    test('should search documents', async ({ page }) => {
      await page.goto('/gpt/rag');

      const searchInput = page.getByPlaceholder(/поиск|search/i);
      if (await searchInput.isVisible()) {
        await searchInput.fill('test document');
        await searchInput.press('Enter');

        // URL should update with search param
        await expect(page).toHaveURL(/q=test/);
      }
    });
  });

  test.describe('Document Upload', () => {
    test('should open upload modal', async ({ page }) => {
      await page.goto('/gpt/rag');

      await page.getByRole('button', { name: /загрузить|upload|добавить/i }).click();

      // Modal should appear
      await expect(
        page.getByRole('dialog').or(page.locator('[role="dialog"]'))
      ).toBeVisible();
    });

    test('should show file picker in upload modal', async ({ page }) => {
      await page.goto('/gpt/rag');

      await page.getByRole('button', { name: /загрузить|upload|добавить/i }).click();

      // File input should be present
      await expect(page.locator('input[type="file"]')).toBeAttached();
    });

    test('should upload a document', async ({ page }) => {
      await page.goto('/gpt/rag');

      await page.getByRole('button', { name: /загрузить|upload|добавить/i }).click();

      // Create a test file
      const fileInput = page.locator('input[type="file"]');
      
      // Upload test file
      await fileInput.setInputFiles({
        name: 'test-document.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('This is a test document content for RAG testing.'),
      });

      // Click upload/confirm button
      const uploadBtn = page.getByRole('button', { name: /загрузить|upload|отправить|submit/i });
      if (await uploadBtn.isVisible()) {
        await uploadBtn.click();

        // Should show success or processing status
        await expect(
          page.getByText(/загружен|uploaded|processing|обработка/i)
        ).toBeVisible({ timeout: 15000 });
      }
    });
  });

  test.describe('Document Details', () => {
    test('should open document details', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Click on first document in list
      const firstDoc = page.locator('[data-testid="doc-row"]').first()
        .or(page.locator('tr').nth(1))
        .or(page.locator('[class*="document"]').first());

      if (await firstDoc.isVisible()) {
        await firstDoc.click();

        // Should show document details
        await expect(
          page.getByText(/статус|status|детали|details/i)
        ).toBeVisible();
      }
    });

    test('should show document status stages', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Click on first document
      const firstDoc = page.locator('[data-testid="doc-row"]').first()
        .or(page.locator('tr').nth(1));

      if (await firstDoc.isVisible()) {
        await firstDoc.click();

        // Should show pipeline stages
        await expect(
          page.getByText(/upload|extract|normalize|chunk|embed/i)
        ).toBeVisible();
      }
    });
  });

  test.describe('Document Actions', () => {
    test('should show action menu for document', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Find action button on first document
      const actionBtn = page.locator('[data-testid="doc-actions"]').first()
        .or(page.locator('button[aria-label*="action"]').first())
        .or(page.locator('[class*="menu"]').first());

      if (await actionBtn.isVisible()) {
        await actionBtn.click();

        // Should show action menu
        await expect(
          page.getByRole('menu').or(page.locator('[role="menu"]'))
        ).toBeVisible();
      }
    });

    test('should be able to delete document', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Find delete button
      const deleteBtn = page.getByRole('button', { name: /удалить|delete/i }).first();

      if (await deleteBtn.isVisible()) {
        await deleteBtn.click();

        // Should show confirmation dialog
        await expect(
          page.getByText(/подтвердите|confirm|уверены/i)
        ).toBeVisible();
      }
    });

    test('should be able to start ingestion', async ({ page }) => {
      await page.goto('/gpt/rag');

      // Find ingest button
      const ingestBtn = page.getByRole('button', { name: /обработать|ingest|запустить/i }).first();

      if (await ingestBtn.isVisible()) {
        await ingestBtn.click();

        // Should start processing or show confirmation
        await expect(
          page.getByText(/обработка|processing|запущен/i)
        ).toBeVisible({ timeout: 10000 });
      }
    });
  });
});
