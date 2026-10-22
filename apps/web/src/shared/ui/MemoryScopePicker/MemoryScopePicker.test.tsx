import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiRequest } from '@/shared/api/http';
import { MemoryScopePicker } from './MemoryScopePicker';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));

it('loads choices from the independent scope API and passes selected project slugs to its caller', async () => {
  vi.mocked(apiRequest).mockResolvedValue([
  {
      id: 'scope',
      key: 'company',
      name: 'Компания',
      aliases: [],
      scope_type: 'project',
      is_all: false,
    },
  ]);
  const onChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryScopePicker value={[]} onChange={onChange} />
    </QueryClientProvider>
  );
  fireEvent.click(await screen.findByRole('checkbox', { name: 'Компания (company)' }));
  expect(apiRequest).toHaveBeenCalledWith('/memory/scopes');
  expect(onChange).toHaveBeenCalledWith(['company']);
});
