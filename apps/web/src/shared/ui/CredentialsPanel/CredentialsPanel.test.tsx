import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  instances: vi.fn(),
  delete: vi.fn(),
}));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('@/shared/api/credentials', () => ({
  credentialsApi: {
    listProfile: mocks.list,
    listSummary: mocks.list,
    list: mocks.list,
    listProfileInstances: mocks.instances,
    deleteProfile: mocks.delete,
  },
}));
vi.mock('@/shared/api/toolInstances', () => ({
  toolInstancesApi: { list: mocks.instances },
}));
vi.mock('../Toast', () => ({
  useErrorToast: () => vi.fn(),
  useSuccessToast: () => vi.fn(),
}));
import { CredentialsPanel } from './CredentialsPanel';

const credential = {
  id: 'credential-1',
  instance_id: 'instance-1',
  auth_type: 'token',
  is_active: true,
  owner_platform: false,
  created_at: '2026-10-28T00:00:00Z',
};
beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue([credential]);
  mocks.instances
    .mockReset()
    .mockResolvedValue([{ id: 'instance-1', name: 'Корпоративная Jira' }]);
  mocks.delete.mockReset();
});
function mount(mode: 'user' | 'readonly-owner' = 'user') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CredentialsPanel
        mode={mode}
        title="Мои учётные данные"
        ownerUserId="user-1"
      />
    </QueryClientProvider>
  );
}
describe('CredentialsPanel presentation', () => {
  it('shows loaded count and identifies the source without deleting on cancel', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByLabelText('Учётных данных: 1');
    await waitFor(() =>
      expect(screen.getAllByText('Корпоративная Jira').length).toBeGreaterThan(
        0
      )
    );
    expect(screen.getByText('API-токен')).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Удалить' })[0]);
    const dialog = screen.getByRole('dialog', {
      name: 'Удалить учётные данные?',
    });
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }));
    expect(mocks.delete).not.toHaveBeenCalled();
  });
  it('preserves readonly capability in both desktop and mobile views', async () => {
    mount('readonly-owner');
    await screen.findByLabelText('Учётных данных: 1');
    expect(
      screen.queryByRole('button', { name: 'Удалить' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Добавить учётные данные' })
    ).not.toBeInTheDocument();
  });
  it('distinguishes an API failure from an empty list and retries', async () => {
    mocks.list.mockRejectedValueOnce(new Error('offline'));
    const user = userEvent.setup();
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось загрузить учётные данные'
    );
    expect(screen.queryByLabelText('Учётных данных: 0')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Повторить' }));
    await screen.findByLabelText('Учётных данных: 1');
  });
  it('disables creating credentials when no source is available', async () => {
    mocks.instances.mockResolvedValue([]);
    mount();
    expect(
      await screen.findByRole('button', { name: 'Добавить учётные данные' })
    ).toBeDisabled();
  });
});
