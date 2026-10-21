import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { collectionsApi, type Collection } from '@/shared/api/collections';
import { apiRequest } from '@/shared/api/http';
import CollectionsListPage from './CollectionsListPage';

vi.mock('@/shared/api/http', () => ({ apiRequest: vi.fn() }));

const persisted = {
  id: 'real-id',
  slug: 'real-data',
  name: 'Настоящая коллекция',
  collection_type: 'table',
  total_rows: 4,
  is_active: true,
  created_at: '',
  updated_at: '',
} as Collection;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={['/gpt/collections']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/gpt/collections" element={<CollectionsListPage />} />
          <Route
            path="/gpt/collections/glossary"
            element={<p>Каталог терминов</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

it('lists persisted collections and keeps the glossary reachable without synthetic memory rows or requests', async () => {
  vi.spyOn(collectionsApi, 'list').mockResolvedValue({
    items: [persisted],
    total: 1,
  });
  setup();
  await screen.findByText('Настоящая коллекция');
  expect(screen.getAllByRole('row')).toHaveLength(2);
  expect(screen.queryByText('Project Memory')).not.toBeInTheDocument();
  expect(screen.queryByText('Глобальная память')).not.toBeInTheDocument();
  expect(apiRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Глоссарий' }));
  expect(screen.getByText('Каталог терминов')).toBeInTheDocument();
});

it('recovers a failed catalogue load through the retry button', async () => {
  vi.spyOn(collectionsApi, 'list')
    .mockRejectedValueOnce(new Error('Network failure'))
    .mockResolvedValue({ items: [persisted], total: 1 });
  setup();
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Не удалось загрузить'
  );
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  await screen.findByText('Настоящая коллекция');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
