import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { collectionsApi } from '@/shared/api/collections';
import { apiRequest } from '@/shared/api/http';
import { ProfileMemoryScopes } from './ProfileMemoryScopes';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));
vi.mock('@/shared/ui/Toast', () => ({
  useErrorToast: () => vi.fn(),
  useSuccessToast: () => vi.fn(),
}));

const catalog = [
  {
    id: '1',
    scope_type: 'team' as const,
    key: 'team.ops',
    name: 'Инфраструктура',
    aliases: [],
    is_all: false,
  },
  {
    id: '2',
    scope_type: 'project' as const,
    key: 'project.nims',
    name: 'NIMS',
    aliases: [],
    is_all: false,
  },
  {
    id: '3',
    scope_type: 'project' as const,
    key: 'project.all',
    name: 'Все проекты',
    aliases: [],
    is_all: true,
  },
];

describe('Profile memory scopes', () => {
  beforeEach(() => {
    vi.spyOn(collectionsApi, 'getMemoryScopeCatalog').mockResolvedValue(
      catalog
    );
    vi.mocked(apiRequest).mockResolvedValue({
      memory_scope_keys: ['team.ops', 'project.nims'],
    });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  function renderPanel(scopeKeys: string[] = []) {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ProfileMemoryScopes
          scopeKeys={scopeKeys}
          tenantScopeKeys={['team.ops']}
        />
      </QueryClientProvider>
    );
  }

  it('shows tenant inheritance and saves concrete teams/projects in the personal profile', async () => {
    const user = userEvent.setup();
    renderPanel();
    const team = await screen.findByRole('checkbox', {
      name: 'Инфраструктура',
    });
    expect(team).not.toBeChecked();
    expect(screen.getByText('Из tenant-а: Инфраструктура')).toBeInTheDocument();
    expect(
      screen.queryByRole('checkbox', { name: 'Все проекты' })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Сохранить скоупы' })
    ).toBeDisabled();
    await user.click(team);
    await user.click(screen.getByRole('checkbox', { name: 'NIMS' }));
    await user.click(screen.getByRole('button', { name: 'Сохранить скоупы' }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith('/profile/memory-scopes', {
        method: 'PUT',
        body: JSON.stringify({
          memory_scope_keys: ['team.ops', 'project.nims'],
        }),
      })
    );
  });

  it('lets the user clear their selection to restore tenant inheritance', async () => {
    const user = userEvent.setup();
    renderPanel(['project.nims']);
    await user.click(await screen.findByRole('checkbox', { name: 'NIMS' }));
    await user.click(screen.getByRole('button', { name: 'Сохранить скоупы' }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith('/profile/memory-scopes', {
        method: 'PUT',
        body: JSON.stringify({ memory_scope_keys: [] }),
      })
    );
  });
});
