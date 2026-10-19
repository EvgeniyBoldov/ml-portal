import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { collectionsApi } from '@/shared/api/collections';
import { apiRequest } from '@/shared/api/http';
import type { ChatContextInspection } from '@/shared/api/chats';
import { ChatMemoryScopes } from './ChatMemoryScopes';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));
const context: ChatContextInspection = {
  revision: 4,
  focus: { scope_keys: ['company'], scope_mode: 'inherit' },
  active_goal: null,
  term_bindings: [],
  artifacts: [],
  open_loops: [],
  decisions: [],
  recent_anchor: null,
  task_results: [],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('Chat memory scope override', () => {
  it('replaces the inherited set and can restore inheritance with an explicit null', async () => {
    vi.spyOn(collectionsApi, 'getMemoryScopeCatalog').mockResolvedValue([
      {
        id: '1',
        key: 'company',
        name: 'Компания',
        aliases: [],
        scope_type: 'project',
        is_all: false,
      },
      {
        id: '2',
        key: 'nims',
        name: 'NIMS',
        aliases: [],
        scope_type: 'project',
        is_all: false,
      },
    ]);
    vi.mocked(apiRequest).mockResolvedValue({
      ...context,
      revision: 5,
      focus: { scope_keys: ['nims'], scope_mode: 'replace' },
    });
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ChatMemoryScopes chatId="chat1" context={context} />
      </QueryClientProvider>
    );
    await user.click(
      await screen.findByRole('checkbox', { name: 'Компания (company)' })
    );
    await user.click(screen.getByRole('checkbox', { name: 'NIMS (nims)' }));
    await user.click(screen.getByRole('button', { name: 'Применить к чату' }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith('/chats/chat1/memory-scopes', {
        method: 'PUT',
        body: JSON.stringify({ scope_keys: ['nims'], expected_revision: 4 }),
      })
    );
    await user.click(
      screen.getByRole('button', { name: 'Использовать настройки профиля' })
    );
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith('/chats/chat1/memory-scopes', {
        method: 'PUT',
        body: JSON.stringify({ scope_keys: null, expected_revision: 4 }),
      })
    );
  });
});
