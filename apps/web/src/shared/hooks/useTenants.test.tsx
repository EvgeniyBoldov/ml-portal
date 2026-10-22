import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ getTenants: vi.fn() }));
vi.mock('@shared/api/tenant', () => ({ tenantApi: { getTenants: mocks.getTenants } }));

import { useTenants } from './useTenants';

const tenant = (id: string) => ({
  id, name: `Tenant ${id}`, memory_scope_keys: [], is_active: true,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
});

afterEach(() => vi.clearAllMocks());
beforeEach(() => {
  mocks.getTenants
    .mockResolvedValueOnce({ items: [tenant('1')], page: 1, size: 100, total: 101, has_more: true })
    .mockResolvedValueOnce({ items: [tenant('2')], page: 2, size: 100, total: 101, has_more: false });
});

describe('useTenants', () => {
  it('sends search to the server and accumulates subsequent pages', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: React.PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useTenants(true, 'Operations'), { wrapper });

    await waitFor(() => expect(result.current.tenants).toHaveLength(1));
    expect(mocks.getTenants).toHaveBeenNthCalledWith(1, {
      page: 1, size: 100, search: 'Operations', include_deprecated: true,
    });

    await act(async () => { await result.current.fetchNextPage(); });

    expect(result.current.tenants.map(row => row.id)).toEqual(['1', '2']);
    expect(mocks.getTenants).toHaveBeenNthCalledWith(2, {
      page: 2, size: 100, search: 'Operations', include_deprecated: true,
    });
    client.clear();
  });
});
