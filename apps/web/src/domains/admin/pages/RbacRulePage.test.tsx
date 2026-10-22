import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  updateRule: vi.fn(),
  rule: {
    id: 'rule-1', level: 'tenant' as const, owner_user_id: null, owner_tenant_id: 'tenant-1', owner_platform: false,
    resource_type: 'agent' as const, resource_id: 'agent-1', effect: 'allow' as const,
    created_at: '2026-01-01T00:00:00Z', created_by_user_id: null, lifecycle_status: 'active',
  },
  enrichedRule: {
    id: 'rule-1', owner: { level: 'tenant' as const, name: 'Tenant One', user_id: null, tenant_id: 'tenant-1', platform: false },
    resource: { type: 'agent' as const, id: 'agent-1', name: 'Agent One', slug: 'agent-one' },
    effect: 'allow' as const, created_at: '2026-01-01T00:00:00Z', created_by_user_id: null, created_by_name: null,
  },
}));

vi.mock('@/shared/api/rbac', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/api/rbac')>()),
  rbacApi: {
    getRule: vi.fn(async () => mocks.rule),
    listEnrichedRules: vi.fn(async () => [mocks.enrichedRule]),
    updateRule: mocks.updateRule,
  },
}));
vi.mock('@/shared/api/admin', () => ({
  adminApi: {
    getUser: vi.fn(async () => ({ id: 'user-1', login: 'alice', tenant_id: 'tenant-1' })),
    getTenant: vi.fn(async () => ({ id: 'tenant-1', name: 'Tenant One' })),
    getUsers: vi.fn(async () => ({ users: [{ id: 'user-1', login: 'alice' }] })),
  },
}));
vi.mock('@/shared/api/tenant', () => ({
  tenantApi: { getTenants: vi.fn(async () => ({ items: [{ id: 'tenant-1', name: 'Tenant One' }] })) },
}));
vi.mock('@/shared/api/agents', () => ({ agentsApi: { list: vi.fn(async () => [{ id: 'agent-1', name: 'Agent One' }]) } }));
vi.mock('@/shared/api/collections', () => ({ default: { listAll: vi.fn(async () => ({ items: [] })) } }));
vi.mock('@/shared/ui/Toast', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/Toast')>()),
  useErrorToast: () => vi.fn(),
  useSuccessToast: () => vi.fn(),
}));
vi.mock('@/shared/ui/LifecycleRestoreDialog', () => ({ default: () => null }));
vi.mock('@/shared/ui', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui')>()),
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  Select: ({ value, onChange, options, placeholder }: {
    value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }>; placeholder?: string;
  }) => <select value={value} onChange={event => onChange(event.target.value)}>
    {placeholder && <option value="">{placeholder}</option>}
    {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
  </select>,
  LifecycleDeleteDialog: () => null,
}));
vi.mock('@/shared/ui/EntityPage', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/EntityPage')>()),
  EntityPageV2: ({ children, onEdit, onSave }: React.PropsWithChildren<{ onEdit?: () => void; onSave?: () => void }>) => (
    <main>{children}<button onClick={onEdit}>Изменить</button><button onClick={onSave}>Сохранить</button></main>
  ),
  Tab: ({ title, children }: React.PropsWithChildren<{ title: string }>) => <section aria-label={title}>{children}</section>,
}));
vi.mock('@/shared/ui/GridLayout', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/GridLayout')>()),
  Block: ({ title, children }: React.PropsWithChildren<{ title: string }>) => <section><h2>{title}</h2>{children}</section>,
}));

import { RbacRulePage } from './RbacRulePage';

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/rbac/rule-1']}>
        <Routes><Route path="/admin/rbac/:id" element={<RbacRulePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mocks.updateRule.mockImplementation(async (_id: string, data: Record<string, unknown>) => ({ ...mocks.rule, ...data }));
});

describe('RbacRulePage', () => {
  it('shows level and owner together in view mode', async () => {
    renderPage();

    expect(await screen.findByText('Тенант: Tenant One')).toBeInTheDocument();
    expect(screen.queryByText('Уровень доступа')).not.toBeInTheDocument();
    expect(screen.queryByText('Владелец уровня')).not.toBeInTheDocument();
  });

  it('updates level and owner together when saving', async () => {
    renderPage();
    await screen.findByText('Тенант: Tenant One');
    await screen.findByText('01.01.2026, 00:00:00');
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));

    await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(5));
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'user' } });
    await waitFor(() => expect(screen.getAllByRole('combobox')[1]).toHaveValue(''));
    await screen.findByRole('option', { name: 'alice' });
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'user-1' } });
    fireEvent.change(screen.getAllByRole('combobox')[3], { target: { value: 'agent-1' } });
    expect(screen.getAllByRole('combobox')[0]).toHaveValue('user');
    expect(screen.getAllByRole('combobox')[1]).toHaveValue('user-1');
    expect(screen.getAllByRole('combobox')[3]).toHaveValue('agent-1');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(mocks.updateRule).toHaveBeenCalledWith('rule-1', {
      level: 'user',
      effect: 'allow',
      resource_type: 'agent',
      resource_id: 'agent-1',
      owner_user_id: 'user-1',
      owner_tenant_id: null,
      owner_platform: false,
    }));
  });
});
