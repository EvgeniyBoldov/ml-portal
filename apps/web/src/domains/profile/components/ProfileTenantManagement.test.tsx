import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/shared/api/http';
import { ProfileTenantManagement } from './ProfileTenantManagement';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));
vi.mock('@/shared/ui/Toast', () => ({ useErrorToast: () => vi.fn(), useSuccessToast: () => vi.fn() }));
vi.mock('@/shared/ui/CredentialsPanel', () => ({
  CredentialsPanel: ({ title, mode, hideCreateButton }: { title: string; mode: string; hideCreateButton?: boolean }) => <header>{title}{mode !== 'tenant-admin' && !hideCreateButton && <button>Добавить credential</button>}</header>,
}));
vi.mock('@/shared/ui/MultiSelectTagPicker/MultiSelectTagPicker', () => ({
  default: ({ value, disabled, onChange }: { value: string[]; disabled?: boolean; onChange: (value: string[]) => void }) => (
    <button disabled={disabled} onClick={() => onChange([...value, 'user-2'])}>Назначить редактора</button>
  ),
}));
vi.mock('@/shared/ui/MemoryScopeSelect/MemoryScopeSelect', () => ({
  MemoryScopeSelect: ({ value, readOnly, onChange }: { value: string[]; readOnly?: boolean; onChange: (value: string[]) => void }) => (
    <div><span>{value.join(', ')}</span>{!readOnly && <button onClick={() => onChange([...value, 'ops'])}>Добавить скоуп</button>}</div>
  ),
}));

const tenantSettings = {
  tenant_id: 'tenant-1',
  memory_scope_keys: ['finance'],
  data_editors: [
    { id: 'user-1', login: 'alice', full_name: 'Alice', is_data_editor: true },
    { id: 'user-2', login: 'bob', full_name: null, is_data_editor: false },
  ],
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ProfileTenantManagement tenantId="tenant-1" /></QueryClientProvider>);
}

beforeEach(() => {
  vi.mocked(apiRequest).mockImplementation(async (path, init) => init?.method === 'PUT' ? {} : tenantSettings as never);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('ProfileTenantManagement', () => {
  it('keeps settings read-only until edit and saves the selected tenant editors and scopes', async () => {
    renderPanel();
    expect(await screen.findByText('Учётные данные рабочей группы')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Редактировать' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: 'Добавить credential' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Назначить редактора' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Редактировать' }));
    fireEvent.click(screen.getByRole('button', { name: 'Назначить редактора' }));
    fireEvent.click(screen.getByRole('button', { name: 'Добавить скоуп' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith('/profile/tenant-management', {
      method: 'PUT',
      body: JSON.stringify({ memory_scope_keys: ['finance', 'ops'], data_editor_user_ids: ['user-1', 'user-2'] }),
    }));
  });
});
