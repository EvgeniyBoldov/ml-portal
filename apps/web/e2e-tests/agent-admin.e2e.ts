import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

const authFile = process.env.AGENT_E2E_AUTH_FILE;
test.skip(!authFile, 'Requires an authenticated platform admin session');

test('create and version an agent, then delete a non-current archived version', async ({ page, context }) => {
  const { refresh_token } = JSON.parse(readFileSync(authFile!, 'utf8'));
  const baseURL = process.env.BASE_URL || 'http://localhost:5173';
  await context.addCookies([{
    name: 'refresh_token',
    value: refresh_token,
    url: baseURL,
    httpOnly: true,
    sameSite: 'Lax',
  }]);
  expect((await context.request.post('/api/v1/auth/refresh')).status()).toBe(200);

  const slug = `agent-admin-e2e-${randomUUID()}`;
  const created = await context.request.post('/api/v1/admin/agents', {
    data: { slug, name: 'Agent admin E2E' },
  });
  expect(created.status()).toBe(201);
  const agent = await created.json();

  try {
    await page.goto(`/admin/agents/${agent.id}/versions/new`);
    await expect(page.getByRole('heading', { name: 'Новая версия' })).toBeVisible();
    await page.getByRole('button', { name: 'Выполнение' }).click();
    await page.getByLabel('Task contracts (JSON)').fill('[{"name":"lookup","inputs":["id"]}]');
    await page.getByRole('checkbox', { name: 'Разрешить динамические контракты' }).uncheck();
    await page.getByRole('checkbox', { name: 'Требовать свежий поиск' }).check();
    await page.getByRole('button', { name: 'Создать', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/admin/agents/${agent.id}/versions/1$`));

    let versionResponse = await context.request.get(`/api/v1/admin/agents/${agent.id}/versions/1`);
    expect(versionResponse.status()).toBe(200);
    let version = await versionResponse.json();
    expect(version.task_contracts).toEqual([{ name: 'lookup', inputs: ['id'] }]);
    expect(version.supports_dynamic_contracts).toBe(false);
    expect(version.requires_fresh_retrieval).toBe(true);

    await page.getByRole('button', { name: 'Опубликовать' }).click();
    await page.getByRole('button', { name: 'Сделать основной' }).click();
    await page.getByRole('button', { name: 'Clone' }).click();
    await page.getByRole('button', { name: 'Создать', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/admin/agents/${agent.id}/versions/2$`));
    await page.getByRole('button', { name: 'Опубликовать' }).click();
    await page.getByRole('button', { name: 'Сделать основной' }).click();

    await page.goto(`/admin/agents/${agent.id}/versions/1`);
    await expect(page.getByRole('button', { name: 'Удалить', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Удалить', exact: true }).click();
    await page.getByRole('button', { name: 'Удалить', exact: true }).last().click();
    await expect(page).toHaveURL(`/admin/agents/${agent.id}`);

    versionResponse = await context.request.get(`/api/v1/admin/agents/${agent.id}/versions/1`);
    expect(versionResponse.status()).toBe(404);
  } finally {
    await context.request.delete(`/api/v1/admin/agents/${agent.id}`);
  }
});
