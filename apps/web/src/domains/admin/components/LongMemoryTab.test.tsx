import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { adminApi } from '@/shared/api/admin';
import LongMemoryTab from './LongMemoryTab';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('LongMemoryTab', () => {
  it('shows the effective no-scope state and document indexing metrics', async () => {
    vi.spyOn(adminApi, 'getMemoryScopes').mockResolvedValue([]);
    vi.spyOn(adminApi, 'getLongMemoryDocuments').mockResolvedValue({
      items: [{
        document_id: 'doc-1', title: 'Без scope', filename: 'manual.pdf', status: 'completed',
        action: 'add', scope_keys: [], metrics: { unique_passages: 4, entities: 3, extracted_triples: 2 },
        error: null, updated_at: null,
      }],
      total: 1, limit: 25, offset: 0,
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><LongMemoryTab /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Без скоупа')).toBeInTheDocument();
    expect(screen.getByText('manual.pdf')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(adminApi.getLongMemoryDocuments).toHaveBeenCalledWith({
      query: undefined, scope_key: undefined, status: undefined, limit: 25, offset: 0,
    });
  });
});
