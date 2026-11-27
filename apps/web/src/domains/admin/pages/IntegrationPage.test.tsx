import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { expect, it, vi } from 'vitest';

import IntegrationPage from './IntegrationPage';

const { api, issue } = vi.hoisted(() => {
  const token = {
    id: 'token', name: 'Kopatych', token_prefix: 'mlp_int_visible',
    is_active: true, expires_at: null, last_used_at: null, created_at: '2026-01-01T00:00:00Z',
  };
  const issue = vi.fn().mockResolvedValue({ ...token, token: 'mlp_int_full_secret' });
  return {
    issue,
    api: {
      get: vi.fn().mockResolvedValue({
        id: 'clouds', name: 'Clouds', source: 'clouds:express', connector_id: 'clouds-connector', is_active: true,
      }),
      tokens: vi.fn().mockResolvedValue([token]),
      issue,
    },
  };
});

vi.mock('@/shared/api/assignmentIntegrations', () => ({ assignmentIntegrationsApi: api }));
vi.mock('@/shared/api/toolInstances', () => ({
  toolInstancesApi: { list: vi.fn().mockResolvedValue([{ id: 'clouds-connector', name: 'Clouds endpoint' }]) },
}));
vi.mock('@/shared/ui/Toast', () => ({ useErrorToast: () => vi.fn(), useSuccessToast: () => vi.fn() }));

it('shows the create and cancel buttons in the header of a new integration', async () => {
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/admin/integrations/new']}>
        <Routes>
          <Route path="/admin/integrations/:id" element={<IntegrationPage />} />
          <Route path="/admin/platform" element={<h1>Настройки платформы</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  expect(screen.getByRole('button', { name: 'Создать' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Отмена' }));
  expect(screen.getByRole('heading', { name: 'Настройки платформы' })).toBeInTheDocument();
});

it('shows the bound connector and reveals the full issued token only in its dialog', async () => {
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/admin/integrations/clouds']}>
        <Routes>
          <Route path="/admin/integrations/:id" element={<IntegrationPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  expect(await screen.findByText('Clouds endpoint')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Токены авторизации' }));
  expect(await screen.findByText('mlp_int_visible…')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Выпустить токен' }));
  const dialog = screen.getByRole('dialog', { name: 'Выпустить токен' });
  await user.type(within(dialog).getByRole('textbox'), 'Копатыч');
  const days = within(dialog).getByRole('spinbutton');
  await user.type(days, '30');
  await user.clear(days);
  await user.click(within(dialog).getByRole('button', { name: 'Выпустить' }));
  expect(issue).toHaveBeenCalledWith('clouds', { name: 'Копатыч', expires_days: null });
  expect(await screen.findByDisplayValue('mlp_int_full_secret')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Готово' }));
  expect(screen.queryByDisplayValue('mlp_int_full_secret')).not.toBeInTheDocument();
});
