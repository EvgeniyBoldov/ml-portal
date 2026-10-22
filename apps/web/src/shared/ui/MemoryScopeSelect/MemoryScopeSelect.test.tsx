import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiRequest } from '@/shared/api/http';
import { MemoryScopeSelect } from './MemoryScopeSelect';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));

it('shows project names in one searchable field and excludes team scopes', async () => {
  vi.mocked(apiRequest).mockResolvedValue([
    { id: 'p1', key: 'company', name: 'Компания', aliases: [], scope_type: 'project', is_all: false },
    { id: 't1', key: 'ops', name: 'Эксплуатация', aliases: ['operations'], scope_type: 'team', is_all: false },
  ]);
  const onChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryScopeSelect value={[]} onChange={onChange} /></QueryClientProvider>);

  const picker = await screen.findByRole('combobox', { name: 'Скоупы памяти чатов' });
  fireEvent.change(picker, { target: { value: 'company' } });
  expect(screen.queryByRole('option', { name: 'Эксплуатация' })).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole('option', { name: 'Компания' }));

  expect(onChange).toHaveBeenCalledWith(['company']);
  expect(screen.getByRole('combobox', { name: 'Скоупы памяти чатов' })).toBeInTheDocument();
});
