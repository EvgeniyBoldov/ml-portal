import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/shared/api/http';
import { ProfileMemoryScopes } from './ProfileMemoryScopes';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));
vi.mock('@/shared/ui/Toast', () => ({ useErrorToast: () => vi.fn(), useSuccessToast: () => vi.fn() }));

const catalog = [
  { id: '1', scope_type: 'project' as const, key: 'ops', name: 'Инфраструктура', aliases: [], is_all: false },
  { id: '2', scope_type: 'project' as const, key: 'nims', name: 'NIMS', aliases: [], is_all: false },
];

describe('ProfileMemoryScopes', () => {
  beforeEach(() => vi.mocked(apiRequest).mockResolvedValue(catalog));
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  function renderScopes(props: React.ComponentProps<typeof ProfileMemoryScopes>) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={queryClient}><ProfileMemoryScopes {...props} /></QueryClientProvider>);
  }

  it('keeps scopes locked until the page enables editing', async () => {
    renderScopes({ scopeKeys: ['ops'], tenantScopeKeys: ['nims'], hasTenant: true });
    const pickers = await screen.findAllByRole('combobox', { name: 'Скоупы памяти чатов' });
    expect(pickers).toHaveLength(1);
    expect(pickers[0]).toBeDisabled();
    expect(screen.getByText('Мои скоупы')).toBeInTheDocument();
    expect(screen.getByText('Скоупы тенанта')).toBeInTheDocument();
  });

  it('reports personal scope edits while tenant scopes stay read-only', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderScopes({ scopeKeys: ['ops'], tenantScopeKeys: ['nims'], hasTenant: true, editable: true, onChange });
    const picker = await screen.findByRole('combobox', { name: 'Скоупы памяти чатов' });
    await user.click(screen.getByRole('button', { name: 'Убрать Инфраструктура' }));
    expect(onChange).toHaveBeenCalledWith([]);
    expect(picker).toBeEnabled();
    expect(screen.getByText('NIMS')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole('combobox', { name: 'Скоупы памяти чатов' })).toHaveLength(1));
  });
});
