import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}));
vi.mock('@shared/api/http', () => ({ apiRequest: mocks.api }));
vi.mock('@shared/ui/Toast', () => ({
  useErrorToast: () => mocks.error,
  useSuccessToast: () => mocks.success,
}));
vi.mock('../components/ProfileMemoryScopes', () => ({
  ProfileMemoryScopes: () => null,
}));
vi.mock('../components/ProfileTenantManagement', () => ({
  ProfileTenantManagement: () => null,
}));
vi.mock('@/shared/ui/CredentialsPanel', () => ({
  CredentialsPanel: () => null,
}));
vi.mock('@/shared/ui/FactsPanel/FactsPanel', () => ({
  FactsPanel: () => null,
}));
import ProfilePage from './ProfilePage';

const profile = {
  id: 'user',
  login: 'admin',
  email: null,
  role: 'admin',
  auth_provider: 'local',
  is_admin: true,
  is_tenant_admin: true,
  created_at: '2026-10-28T00:00:00Z',
  tenants: ['tenant'],
  memory_scope_keys: [],
  tenant_memory_scope_keys: [],
};

beforeEach(() => {
  mocks.api.mockReset();
  mocks.error.mockReset();
  mocks.success.mockReset();
  mocks.api.mockImplementation(async (path: string) =>
    path === '/profile/me' ? profile : []
  );
});

function mount() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProfilePage />
    </QueryClientProvider>
  );
}

describe('profile password form', () => {
  it('links field errors to the labelled inputs without sending invalid passwords', async () => {
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByRole('button', { name: 'Сменить пароль' })
    );
    const dialog = screen.getByRole('dialog', { name: 'Сменить пароль' });
    const current = within(dialog).getByLabelText('Текущий пароль');
    const next = within(dialog).getByLabelText('Новый пароль', { exact: true });
    const confirm = within(dialog).getByLabelText('Повторите новый пароль');
    await user.click(
      within(dialog).getByRole('button', { name: 'Сменить пароль' })
    );
    expect(current).toHaveFocus();
    for (const input of [current, next, confirm]) {
      expect(input).toHaveAttribute('aria-invalid', 'true');
      expect(
        document.getElementById(input.getAttribute('aria-describedby') || '')
      ).toHaveAttribute('role', 'alert');
    }
    expect(
      mocks.api.mock.calls.filter(([path]) => path === '/profile/password')
    ).toHaveLength(0);
    expect(mocks.error).not.toHaveBeenCalled();
  });

  it('shows password mismatch inline and clears secret drafts when the modal closes', async () => {
    const user = userEvent.setup();
    mount();
    const opener = await screen.findByRole('button', {
      name: 'Сменить пароль',
    });
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Сменить пароль' });
    await user.type(screen.getByLabelText('Текущий пароль'), 'existing');
    await user.type(
      screen.getByLabelText('Новый пароль', { exact: true }),
      'new-password'
    );
    await user.type(
      screen.getByLabelText('Повторите новый пароль'),
      'mismatch'
    );
    await user.click(
      within(dialog).getByRole('button', { name: 'Сменить пароль' })
    );
    expect(screen.getByLabelText('Повторите новый пароль')).toHaveFocus();
    expect(screen.getByText('Новые пароли не совпадают')).toHaveAttribute(
      'role',
      'alert'
    );
    await user.keyboard('{Escape}');
    expect(opener).toHaveFocus();
    await user.click(opener);
    expect(screen.getByLabelText('Текущий пароль')).toHaveValue('');
    expect(
      screen.queryByText('Новые пароли не совпадают')
    ).not.toBeInTheDocument();
  });

  it('keeps a rejected current password error linked to its field', async () => {
    mocks.api.mockImplementation(async (path: string) => {
      if (path === '/profile/password')
        throw new Error('invalid_current_password');
      return path === '/profile/me' ? profile : [];
    });
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByRole('button', { name: 'Сменить пароль' })
    );
    await user.type(screen.getByLabelText('Текущий пароль'), 'existing');
    await user.type(
      screen.getByLabelText('Новый пароль', { exact: true }),
      'new-password'
    );
    await user.type(
      screen.getByLabelText('Повторите новый пароль'),
      'new-password'
    );
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Сменить пароль',
      })
    );
    await waitFor(() =>
      expect(screen.getByText('Текущий пароль указан неверно')).toHaveAttribute(
        'role',
        'alert'
      )
    );
    expect(screen.getByLabelText('Текущий пароль')).toHaveFocus();
    expect(mocks.error).not.toHaveBeenCalled();
  });
});
