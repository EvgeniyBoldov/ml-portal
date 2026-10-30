import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn() }));

vi.mock('@tanstack/react-query', async importOriginal => ({
  ...(await importOriginal<typeof import('@tanstack/react-query')>()),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock('@shared/api/hooks/useAdmin', () => ({
  useTenant: () => ({ data: undefined, isLoading: false, refetch: vi.fn() }),
  useModels: () => ({ data: { items: [] } }),
  useUsers: () => ({ data: { pages: [{ users: [] }] } }),
  useCreateTenant: () => ({ mutateAsync: mocks.create }),
  useUpdateTenant: () => ({ mutateAsync: mocks.update }),
}));
vi.mock('@/shared/ui/Toast', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/Toast')>()),
  useErrorToast: () => vi.fn(),
  useSuccessToast: () => vi.fn(),
}));
vi.mock('@/shared/ui', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui')>()),
  LifecycleDeleteDialog: () => null,
  CredentialsPanel: () => null,
  FactsPanel: () => null,
}));
vi.mock('@/shared/ui/LifecycleRestoreDialog', () => ({ default: () => null }));
vi.mock('@/shared/ui/MemoryScopeSelect/MemoryScopeSelect', () => ({
  MemoryScopeSelect: ({ value, onChange, readOnly }: { value: string[]; onChange: (keys: string[]) => void; readOnly?: boolean }) => (
    <div>
      <span>Выбранные скоупы: {value.join(', ') || '—'}</span>
      {!readOnly && <button onClick={() => onChange([...value, 'ops'])}>Добавить scope</button>}
    </div>
  ),
}));
vi.mock('@/shared/ui/EntityPage', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/EntityPage')>()),
  EntityPageV2: ({ children, onSave, onCancel }: React.PropsWithChildren<{ onSave?: () => void; onCancel?: () => void }>) => (
    <main>{children}<button onClick={onSave}>Создать</button><button onClick={onCancel}>Отмена</button></main>
  ),
  Tab: ({ title, children }: React.PropsWithChildren<{ title: string }>) =>
    title === 'Создание' ? <section aria-label={title}>{children}</section> : null,
}));
vi.mock('@/shared/ui/GridLayout', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/ui/GridLayout')>();
  return {
    ...actual,
    Block: ({ title, fields = [], data = {}, editable, onChange }: {
      title: string;
      fields?: import('@/shared/ui/GridLayout').FieldConfig[];
      data?: Record<string, unknown>;
      editable?: boolean;
      onChange?: (key: string, value: unknown) => void;
    }) => (
      <section><h2>{title}</h2>{fields.map(field => <label key={field.key}>{field.label}
        {field.type === 'custom'
          ? field.render?.(data[field.key], Boolean(editable), value => onChange?.(field.key, value))
          : field.type === 'select'
          ? <select aria-label={field.label} value={String(data[field.key] ?? '')} disabled={!editable} onChange={event => onChange?.(field.key, event.target.value)}>
              {field.options?.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          : <input aria-label={field.label} value={String(data[field.key] ?? '')} disabled={!editable} onChange={event => onChange?.(field.key, event.target.value)} />}
      </label>)}</section>
    ),
  };
});

import { TenantPage } from './TenantPage';

afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); mocks.create.mockResolvedValue({}); });

describe('TenantPage', () => {
  it('does not expose the removed memory-scope setting and sends an unset model as null', async () => {
    render(<MemoryRouter initialEntries={['/admin/tenants/new']}><Routes>
      <Route path="/admin/tenants/:id" element={<TenantPage />} />
      <Route path="/admin/tenants" element={<div>Tenant list</div>} />
    </Routes></MemoryRouter>);

    const infoHeading = screen.getByRole('heading', { name: 'Основная информация' });
    const infoBlock = infoHeading.closest('section');
    expect(infoBlock).not.toHaveTextContent(/скоупы памяти/i);
    expect(screen.queryByRole('button', { name: /скоупы памяти/i })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Название' }), { target: { value: 'Operations' } });
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({
      name: 'Operations',
      description: null,
      is_active: true,
      extra_embed_model: null,
    }));
  });
});
