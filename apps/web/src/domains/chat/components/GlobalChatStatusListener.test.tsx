import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  auth: { current: { user: { id: 'user-1' }, isAuthReady: true } as {
    user: { id: string } | null;
    isAuthReady: boolean;
  } },
  fetchStatus: vi.fn(),
}));

vi.mock('@/shared/hooks/useAuth', () => ({ useAuth: () => mocks.auth.current }));
vi.mock('@/shared/ui/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/shared/api/chats', () => ({ fetchChatStatusEvents: mocks.fetchStatus }));

import { GlobalChatStatusListener, parseChatStatusSnapshot } from './GlobalChatStatusListener';

beforeEach(() => {
  mocks.auth.current = { user: { id: 'user-1' }, isAuthReady: true };
  mocks.fetchStatus.mockReset();
});

describe('parseChatStatusSnapshot', () => {
  it('accepts only the content-free lifecycle fields', () => {
    expect(parseChatStatusSnapshot(JSON.stringify([{
      chat_id: 'chat-1',
      run_id: 'run-1',
      status: 'running',
      stage: 'executing',
      updated_at: '2026-10-27T10:00:00Z',
      stage_updated_at: '2026-10-27T10:01:00Z',
      content: 'must not enter the status cache',
    }]))).toEqual([{
      chat_id: 'chat-1',
      run_id: 'run-1',
      status: 'running',
      stage: 'executing',
      updated_at: '2026-10-27T10:00:00Z',
      stage_updated_at: '2026-10-27T10:01:00Z',
    }]);
  });

  it('rejects malformed or unknown lifecycle states', () => {
    expect(parseChatStatusSnapshot('{')).toBeNull();
    expect(parseChatStatusSnapshot(JSON.stringify([{
      chat_id: 'chat-1', run_id: null, status: 'working', stage: null,
    }]))).toBeNull();
  });

  it('reconciles an empty authoritative snapshot', () => {
    expect(parseChatStatusSnapshot('[]')).toEqual([]);
  });

  it('aborts the authenticated stream when the user logs out', async () => {
    let streamSignal: AbortSignal | undefined;
    mocks.fetchStatus.mockImplementation((signal?: AbortSignal) => {
      streamSignal = signal;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={queryClient}>
        <GlobalChatStatusListener />
      </QueryClientProvider>
    );

    await waitFor(() => expect(mocks.fetchStatus).toHaveBeenCalledOnce());
    mocks.auth.current = { user: null, isAuthReady: true };
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <GlobalChatStatusListener />
      </QueryClientProvider>
    );

    await waitFor(() => expect(streamSignal?.aborted).toBe(true));
    view.unmount();
    queryClient.clear();
  });
});
