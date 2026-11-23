import { expect, type BrowserContext } from '@playwright/test';
import { readFileSync } from 'node:fs';

export async function signIn(context: BrowserContext, authFile: string) {
  const { login, password } = JSON.parse(readFileSync(authFile, 'utf8'));
  const response = await context.request.post('/api/v1/auth/login', {
    data: { login, password },
  });
  expect(response.status(), 'E2E login status').toBe(200);
  const { access_token: accessToken } = await response.json();
  return accessToken as string;
}
