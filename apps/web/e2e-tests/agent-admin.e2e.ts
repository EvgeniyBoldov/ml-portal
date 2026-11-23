import { expect, test } from '@playwright/test';
import { signIn } from './auth';
import { randomUUID } from 'node:crypto';

const authFile = process.env.AGENT_E2E_AUTH_FILE;
test.skip(!authFile, 'Requires an authenticated platform admin session');

test('create and version an agent, then delete a non-current archived version', async ({ page, context }) => {
  await signIn(context, authFile!);

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
    const dynamicContracts = page.getByRole('checkbox', { name: 'Разрешить динамические контракты' });
    const freshRetrieval = page.getByRole('checkbox', { name: 'Требовать свежий поиск' });
    await expect(dynamicContracts).toBeChecked();
    await dynamicContracts.press('Space');
    await expect(dynamicContracts).not.toBeChecked();
    await expect(freshRetrieval).not.toBeChecked();
    await freshRetrieval.press('Space');
    await expect(freshRetrieval).toBeChecked();
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
