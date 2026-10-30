import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  create: vi.fn(),
  user: {
    id: 'user-1', login: 'alice', full_name: 'Alice', email: 'alice@example.test', role: 'reader', is_admin: false,
    is_active: true, auth_provider: 'ldap', tenant_id: 'tenant-1', memory_scope_keys: ['ops'],
    lifecycle_status: 'active', created_at: '2026-01-01T00:00:00Z',
  },
}));

vi.mock('@tanstack/react-query', async importOriginal => ({
  ...(await importOriginal<typeof import('@tanstack/react-query')>()),
  useQuery: () => ({ data: [
    { id: 'ops-id', key: 'ops', name: 'Operations', scope_type: 'project', aliases: [], is_all: false },
    { id: 'finance-id', key: 'finance', name: 'Finance', scope_type: 'project', aliases: [], is_all: false },
  ] }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock('@shared/api/hooks/useAdmin', () => ({
  useUser: () => ({ data: mocks.user, isLoading: false, refetch: vi.fn() }),
  useUpdateUser: () => ({ mutateAsync: mocks.update }),
  useCreateUser: () => ({ mutateAsync: mocks.create }),
  useSetUserPassword: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock('@shared/hooks/useTenants', () => ({ useTenants: () => ({ tenants: [{ id: 'tenant-1', name: 'Tenant One' }] }) }));
vi.mock('@/shared/ui/Toast', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/Toast')>()),
  useErrorToast: () => vi.fn(),
  useSuccessToast: () => vi.fn(),
}));
vi.mock('@/shared/ui', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui')>()),
  CredentialsPanel: () => null,
  FactsPanel: () => null,
  LifecycleDeleteDialog: () => null,
  LifecycleRestoreDialog: () => null,
  RBACRulesTable: () => null,
}));
vi.mock('@/shared/ui/EntityPage', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/EntityPage')>()),
  EntityPageV2: ({ children, title, onSave, onCancel }: React.PropsWithChildren<{ title?: string; onSave?: () => void; onCancel?: () => void }>) => (
    <main><h1>{title}</h1>{children}<button onClick={onSave}>Сохранить</button><button onClick={onCancel}>Отмена</button></main>
  ),
  Tab: ({ title, actions, children }: React.PropsWithChildren<{ title: string; actions?: React.ReactNode }>) =>
    title === 'Обзор' || title === 'Создание'
      ? <section aria-label={title}>{actions}{children}</section>
      : null,
}));
vi.mock('@/shared/ui/GridLayout', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/ui/GridLayout')>();
  const React = await import('react');
  const { Tags } = await import('@/shared/ui/Tags');
  return {
    ...actual,
    Block: ({ title, fields = [], data = {}, editable, onChange }: any) => (
      <section><h2>{title}</h2>{fields.map((field: any) => <label key={field.key}>{field.label}
        {field.type === 'custom'
          ? field.render?.(data[field.key], Boolean(editable), (value: unknown) => onChange?.(field.key, value))
          : field.type === 'tags'
          ? <Tags value={data[field.key] ?? []} options={field.options} placeholder={field.placeholder} disabled={!editable} onChange={value => onChange?.(field.key, value)} />
          : field.type === 'select'
            ? <select aria-label={field.label} disabled={!editable} value={data[field.key] ?? ''} onChange={event => onChange?.(field.key, event.target.value)}>{field.options?.map((option: any) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
            : <input aria-label={field.label} disabled={!editable} value={data[field.key] ?? ''} onChange={event => onChange?.(field.key, event.target.value)} />}
      </label>)}</section>
    ),
  };
});

import { UserPage } from './UserPage';

afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); mocks.update.mockResolvedValue(mocks.user); });

describe('UserPage', () => {
  it('shows the name as the primary title and does not expose user memory scopes', () => {
    render(<MemoryRouter initialEntries={['/admin/users/user-1']}><Routes><Route path="/admin/users/:id" element={<UserPage />} /></Routes></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Основная информация' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Tenant One' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Alice' })).toBeInTheDocument();
    expect(screen.queryByText(/скоупы памяти/i)).not.toBeInTheDocument();
  });

  it('allows local account identity fields to be edited and saves them', async () => {
    mocks.user.auth_provider = 'local';
    render(<MemoryRouter initialEntries={['/admin/users/user-1']}><Routes><Route path="/admin/users/:id" element={<UserPage />} /></Routes></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Имя' }), { target: { value: 'Alice Smith' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Логин' }), { target: { value: 'alice.smith' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'alice.smith@example.test' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Сохранить' })[0]);

    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith({
      id: 'user-1',
      data: {
        login: 'alice.smith', full_name: 'Alice Smith', email: 'alice.smith@example.test',
        is_admin: false, is_active: true, tenant_id: 'tenant-1',
      },
    }));
  });

  it('collects a name when creating a user', async () => {
    render(<MemoryRouter initialEntries={['/admin/users/new']}><Routes><Route path="/admin/users/:id" element={<UserPage />} /></Routes></MemoryRouter>);

    fireEvent.change(screen.getByRole('textbox', { name: 'Имя' }), { target: { value: 'Alice Smith' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Логин' }), { target: { value: 'alice.smith' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'alice.smith@example.test' } });
    fireEvent.change(screen.getByLabelText('Пароль локальной учётной записи'), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      login: 'alice.smith', full_name: 'Alice Smith', email: 'alice.smith@example.test', password: 'password123',
    })));
  });
});
