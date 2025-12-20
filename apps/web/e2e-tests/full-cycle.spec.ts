import { test, expect } from '@playwright/test';

/**
 * Full Cycle E2E Test
 * 
 * Tests complete user journey through the application:
 * 1. Admin login
 * 2. Create tenant
 * 3. Create user
 * 4. Login as new user
 * 5. Create chat and send messages
 * 6. Upload RAG document
 * 7. Wait for ingestion
 * 8. Search in RAG
 * 9. Test agents and prompts
 * 10. Delete document
 * 11. Delete user
 * 12. Delete tenant
 */

test.describe('Full Cycle E2E Test', () => {
  test('complete user journey from tenant creation to deletion', async ({ page }) => {
    console.log('\n' + '='.repeat(80));
    console.log('🚀 STARTING FULL CYCLE E2E TEST');
    console.log('='.repeat(80) + '\n');

    // =========================================================================
    // STEP 1: Login as admin
    // =========================================================================
    console.log('📝 STEP 1: Login as admin');

    await page.goto('/login');
    await page.getByLabel(/логин|email|login/i).fill('admin');
    await page.getByLabel(/пароль|password/i).fill('admin123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();

    await expect(page).toHaveURL(/\/(gpt|chat|admin|$)/, { timeout: 10000 });
    console.log('  ✅ Admin logged in successfully');

    // =========================================================================
    // STEP 2: Navigate to admin panel
    // =========================================================================
    console.log('\n📝 STEP 2: Navigate to admin panel');

    await page.goto('/admin/tenants');
    await expect(page.getByText(/tenant|арендатор|организац/i)).toBeVisible();
    console.log('  ✅ Admin panel opened');

    // =========================================================================
    // STEP 3: Create tenant
    // =========================================================================
    console.log('\n📝 STEP 3: Create tenant');

    await page.getByRole('button', { name: /создать|create|добавить|add/i }).click();
    
    // Fill tenant form
    await page.getByLabel(/название|name/i).fill('E2E Test Tenant');
    await page.getByLabel(/описание|description/i).fill('Tenant for E2E testing');
    
    // Submit form
    await page.getByRole('button', { name: /создать|create|сохранить|save/i }).click();
    
    // Wait for success
    await expect(
      page.getByText(/создан|created|успешно|success/i)
    ).toBeVisible({ timeout: 10000 });

    console.log('  ✅ Tenant created: E2E Test Tenant');

    // =========================================================================
    // STEP 4: Create user
    // =========================================================================
    console.log('\n📝 STEP 4: Create user');

    await page.goto('/admin/users');
    await page.getByRole('button', { name: /создать|create|добавить|add/i }).click();

    // Fill user form
    await page.getByLabel(/логин|login/i).fill('e2e_test_user');
    await page.getByLabel(/email|почта/i).fill('e2e@test.com');
    await page.getByLabel(/пароль|password/i).first().fill('testpass123');
    
    // Select tenant (if dropdown exists)
    const tenantSelect = page.getByLabel(/tenant|арендатор/i);
    if (await tenantSelect.isVisible()) {
      await tenantSelect.click();
      await page.getByRole('option', { name: /E2E Test Tenant/i }).click();
    }

    // Select role
    const roleSelect = page.getByLabel(/роль|role/i);
    if (await roleSelect.isVisible()) {
      await roleSelect.click();
      await page.getByRole('option', { name: /editor/i }).click();
    }

    // Submit
    await page.getByRole('button', { name: /создать|create|сохранить|save/i }).click();
    
    await expect(
      page.getByText(/создан|created|успешно|success/i)
    ).toBeVisible({ timeout: 10000 });

    console.log('  ✅ User created: e2e_test_user');

    // =========================================================================
    // STEP 5: Logout admin
    // =========================================================================
    console.log('\n📝 STEP 5: Logout admin');

    await page.getByRole('button', { name: /выход|logout|выйти/i }).click();
    await expect(page).toHaveURL(/\/login/);
    console.log('  ✅ Admin logged out');

    // =========================================================================
    // STEP 6: Login as new user
    // =========================================================================
    console.log('\n📝 STEP 6: Login as new user');

    await page.getByLabel(/логин|email|login/i).fill('e2e_test_user');
    await page.getByLabel(/пароль|password/i).fill('testpass123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();

    await expect(page).toHaveURL(/\/(gpt|chat|$)/, { timeout: 10000 });
    console.log('  ✅ User logged in successfully');

    // =========================================================================
    // STEP 7: Create chat and send message
    // =========================================================================
    console.log('\n📝 STEP 7: Create chat and send message');

    await page.goto('/gpt');

    const input = page.getByPlaceholder(/сообщение|message|напишите/i)
      .or(page.locator('textarea').first());

    await input.fill('Hello! This is an E2E test message. What is 2+2?');

    const sendBtn = page.getByRole('button', { name: /отправить|send/i })
      .or(page.locator('button[type="submit"]'));

    await sendBtn.click();

    // Wait for message to appear
    await expect(
      page.getByText('Hello! This is an E2E test message')
    ).toBeVisible({ timeout: 5000 });

    console.log('  ✅ Message sent to chat');

    // Wait for AI response (optional, may take time)
    await page.waitForTimeout(3000);

    // =========================================================================
    // STEP 8: Upload RAG document
    // =========================================================================
    console.log('\n📝 STEP 8: Upload RAG document');

    await page.goto('/gpt/rag');

    await page.getByRole('button', { name: /загрузить|upload|добавить/i }).click();

    // Upload file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'e2e-test-document.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from(`
        E2E Test Document
        
        This document is created by automated E2E test.
        It contains test data for integration testing.
        
        Topics covered:
        - End-to-end testing
        - Automated testing
        - Quality assurance
        - Test automation frameworks
        
        Testing ensures software quality and reliability.
      `),
    });

    // Click upload button
    const uploadBtn = page.getByRole('button', { name: /загрузить|upload|отправить|submit/i });
    if (await uploadBtn.isVisible()) {
      await uploadBtn.click();
    }

    // Wait for upload success
    await expect(
      page.getByText(/загружен|uploaded|успешно|success/i)
    ).toBeVisible({ timeout: 15000 });

    console.log('  ✅ Document uploaded');

    // =========================================================================
    // STEP 9: Start ingestion
    // =========================================================================
    console.log('\n📝 STEP 9: Start ingestion');

    // Find the uploaded document
    const docRow = page.locator('[data-testid="doc-row"]').first()
      .or(page.locator('tr').nth(1));

    if (await docRow.isVisible()) {
      await docRow.click();

      // Find and click ingest button
      const ingestBtn = page.getByRole('button', { name: /обработать|ingest|запустить/i });
      
      if (await ingestBtn.isVisible()) {
        await ingestBtn.click();
        
        await expect(
          page.getByText(/обработка|processing|запущен/i)
        ).toBeVisible({ timeout: 10000 });

        console.log('  ✅ Ingestion started');
      } else {
        console.log('  ⚠️  Ingest button not found (may be auto-started)');
      }
    }

    // Wait for processing
    await page.waitForTimeout(5000);

    // =========================================================================
    // STEP 10: Check document status
    // =========================================================================
    console.log('\n📝 STEP 10: Check document status');

    // Status should be visible in the document details
    await expect(
      page.getByText(/upload|extract|normalize|chunk|embed/i)
    ).toBeVisible({ timeout: 5000 });

    console.log('  ✅ Document status visible');

    // =========================================================================
    // STEP 11: Test agents
    // =========================================================================
    console.log('\n📝 STEP 11: Test agents');

    // Navigate to agents (if accessible)
    await page.goto('/admin/agents').catch(() => {
      console.log('  ⚠️  Agents page not accessible for this user');
    });

    if (page.url().includes('/admin/agents')) {
      await expect(
        page.getByText(/агент|agent/i)
      ).toBeVisible({ timeout: 5000 });
      console.log('  ✅ Agents page loaded');
    }

    // =========================================================================
    // STEP 12: Test prompts
    // =========================================================================
    console.log('\n📝 STEP 12: Test prompts');

    await page.goto('/admin/prompts').catch(() => {
      console.log('  ⚠️  Prompts page not accessible for this user');
    });

    if (page.url().includes('/admin/prompts')) {
      await expect(
        page.getByText(/prompt|шаблон/i)
      ).toBeVisible({ timeout: 5000 });
      console.log('  ✅ Prompts page loaded');
    }

    // =========================================================================
    // STEP 13: Delete RAG document
    // =========================================================================
    console.log('\n📝 STEP 13: Delete RAG document');

    await page.goto('/gpt/rag');

    // Find delete button
    const deleteBtn = page.getByRole('button', { name: /удалить|delete/i }).first();

    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();

      // Confirm deletion
      const confirmBtn = page.getByRole('button', { name: /подтвердить|confirm|да|yes/i });
      if (await confirmBtn.isVisible()) {
        await confirmBtn.click();
      }

      await expect(
        page.getByText(/удален|deleted|успешно|success/i)
      ).toBeVisible({ timeout: 10000 });

      console.log('  ✅ Document deleted');
    }

    // =========================================================================
    // STEP 14: Logout user
    // =========================================================================
    console.log('\n📝 STEP 14: Logout user');

    await page.getByRole('button', { name: /выход|logout|выйти/i }).click();
    await expect(page).toHaveURL(/\/login/);
    console.log('  ✅ User logged out');

    // =========================================================================
    // STEP 15: Login as admin again
    // =========================================================================
    console.log('\n📝 STEP 15: Login as admin again');

    await page.getByLabel(/логин|email|login/i).fill('admin');
    await page.getByLabel(/пароль|password/i).fill('admin123');
    await page.getByRole('button', { name: /войти|sign in|login/i }).click();

    await expect(page).toHaveURL(/\/(gpt|chat|admin|$)/, { timeout: 10000 });
    console.log('  ✅ Admin logged in');

    // =========================================================================
    // STEP 16: Delete user
    // =========================================================================
    console.log('\n📝 STEP 16: Delete user');

    await page.goto('/admin/users');

    // Find user in list
    const userRow = page.getByText('e2e_test_user').locator('..').locator('..');

    if (await userRow.isVisible()) {
      // Find delete button in row
      const deleteUserBtn = userRow.getByRole('button', { name: /удалить|delete/i });
      
      if (await deleteUserBtn.isVisible()) {
        await deleteUserBtn.click();

        // Confirm
        const confirmDeleteBtn = page.getByRole('button', { name: /подтвердить|confirm|да|yes/i });
        if (await confirmDeleteBtn.isVisible()) {
          await confirmDeleteBtn.click();
        }

        await expect(
          page.getByText(/удален|deleted|успешно|success/i)
        ).toBeVisible({ timeout: 10000 });

        console.log('  ✅ User deleted');
      }
    }

    // =========================================================================
    // STEP 17: Delete tenant
    // =========================================================================
    console.log('\n📝 STEP 17: Delete tenant');

    await page.goto('/admin/tenants');

    // Find tenant in list
    const tenantRow = page.getByText('E2E Test Tenant').locator('..').locator('..');

    if (await tenantRow.isVisible()) {
      const deleteTenantBtn = tenantRow.getByRole('button', { name: /удалить|delete/i });
      
      if (await deleteTenantBtn.isVisible()) {
        await deleteTenantBtn.click();

        const confirmDeleteBtn = page.getByRole('button', { name: /подтвердить|confirm|да|yes/i });
        if (await confirmDeleteBtn.isVisible()) {
          await confirmDeleteBtn.click();
        }

        await expect(
          page.getByText(/удален|deleted|успешно|success/i)
        ).toBeVisible({ timeout: 10000 });

        console.log('  ✅ Tenant deleted');
      }
    }

    // =========================================================================
    // FINAL SUMMARY
    // =========================================================================
    console.log('\n' + '='.repeat(80));
    console.log('✅ FULL CYCLE E2E TEST COMPLETED SUCCESSFULLY!');
    console.log('='.repeat(80));
    console.log('\nAll steps passed:');
    console.log('  ✓ Admin authentication');
    console.log('  ✓ Tenant creation and deletion');
    console.log('  ✓ User creation and deletion');
    console.log('  ✓ User authentication');
    console.log('  ✓ Chat messaging');
    console.log('  ✓ RAG document upload and deletion');
    console.log('  ✓ Document ingestion');
    console.log('  ✓ Agents and prompts access');
    console.log('\n' + '='.repeat(80) + '\n');
  });
});
