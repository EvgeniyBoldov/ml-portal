import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

const authFile = process.env.MEMORY_SCOPE_E2E_AUTH_FILE;
test.skip(!authFile, 'Requires an authenticated platform admin session');

test('admin can create, edit, inspect dependencies, and delete a memory scope', async ({ page, context }) => {
  const { refresh_token } = JSON.parse(readFileSync(authFile!, 'utf8'));
  const baseURL = process.env.BASE_URL || 'http://localhost:5173';
  await context.addCookies([{
    name: 'refresh_token', value: refresh_token, url: baseURL, httpOnly: true, sameSite: 'Lax',
  }]);
  expect((await context.request.post('/api/v1/auth/refresh')).status()).toBe(200);

  const key = `scope-e2e-${randomUUID().replaceAll('-', '')}`;
  const initialName = `Scope test ${key.slice(-8)}`;
  const editedName = `${initialName} edited`;
  const created = await context.request.post('/api/v1/admin/memory/scopes', {
    data: { scope_type: 'project', key, name: initialName, aliases: [], is_all: false, project_type: 'e2e' },
  });
  expect(created.status()).toBe(201);
  const scope = await created.json();

  let deleted = false;
  try {
    await page.goto('/admin/memory?tab=scopes');
    await page.getByPlaceholder('Название').fill(initialName);
    await expect(page.getByText(initialName, { exact: true })).toBeVisible();

    await page.getByRole('button', { name: `Действия со скоупом ${initialName}` }).click();
    await page.getByRole('menuitem', { name: 'Изменить' }).click();
    await page.getByLabel('Название').fill(editedName);
    await page.getByLabel('Тип проекта').fill('e2e-updated');
    await page.getByRole('button', { name: 'Сохранить' }).click();
    await expect(page.getByText(editedName, { exact: true })).toBeVisible();

    const dependenciesResponse = page.waitForResponse(response =>
      response.url().includes(`/api/v1/admin/lifecycle/memory_scope/${scope.id}/dependencies`),
    );
    await page.getByRole('button', { name: `Действия со скоупом ${editedName}` }).click();
    await page.getByRole('menuitem', { name: 'Удалить' }).click();
    expect((await dependenciesResponse).status()).toBe(200);
    await page.getByRole('button', { name: 'Удалить скоуп и очистить LongMemory' }).click();
    await expect(page.getByText(editedName, { exact: true })).toHaveCount(0);
    deleted = true;

    const catalog = await context.request.get('/api/v1/admin/memory/scopes');
    expect(catalog.status()).toBe(200);
    expect((await catalog.json()).some((item: { id: string }) => item.id === scope.id)).toBe(false);

    const longMemoryResponse = page.waitForResponse(response =>
      response.url().includes('/api/v1/admin/memory/long-memory/documents'),
    );
    await page.getByText('LongMemory', { exact: true }).click();
    expect(longMemoryResponse.status()).toBe(200);
    await expect(page.getByRole('table')).toBeVisible();
  } finally {
    if (!deleted) {
      await context.request.delete(`/api/v1/admin/lifecycle/memory_scope/${scope.id}?mode=hard&force=true&cascade=true`);
    }
  }
});
