import { fireEvent, render, screen, within } from '@testing-library/react';
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

it('lists persisted collections without synthetic memory rows or a glossary action', async () => {
  vi.spyOn(collectionsApi, 'list').mockResolvedValue({
    items: [persisted],
    total: 1,
  });
  setup();
  await screen.findByText('Настоящая коллекция');
  expect(screen.getAllByRole('row')).toHaveLength(2);
  expect(screen.queryByText('Project Memory')).not.toBeInTheDocument();
  expect(screen.queryByText('Глобальная память')).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Глоссарий' })
  ).not.toBeInTheDocument();
  expect(apiRequest).not.toHaveBeenCalled();
});

it('shows an external source and published description, with an unknown count', async () => {
  vi.spyOn(collectionsApi, 'list').mockResolvedValue({
    items: [
      {
        ...persisted,
        id: 'jira-id',
        slug: 'jira',
        name: 'Jira',
        collection_type: 'api',
        total_rows: 0,
        source: { name: 'Jira Prod', type: 'api' },
        description: 'Задачи и проекты Jira',
        version: { number: 3, status: 'published' },
        count: { value: null, kind: null, unit: null },
      },
    ],
    total: 1,
  });
  setup();

  const row = await screen.findByRole('row', { name: /Jira/ });
  expect(within(row).getByText('Источник: Jira Prod')).toBeInTheDocument();
  expect(within(row).getByText('Задачи и проекты Jira')).toBeInTheDocument();
  expect(within(row).getAllByRole('cell')[3]).toHaveTextContent('—');

  fireEvent.change(screen.getByPlaceholderText('Поиск коллекций...'), {
    target: { value: 'Jira Prod' },
  });
  expect(screen.getByRole('row', { name: /Jira/ })).toBeInTheDocument();
});

it('searches external collections by source and published description', async () => {
  vi.spyOn(collectionsApi, 'list').mockResolvedValue({
    items: [
      {
        ...persisted,
        id: 'jira-id',
        slug: 'jira',
        name: 'Jira',
        collection_type: 'api',
        source: { name: 'Jira Prod', type: 'api' },
        description: 'Задачи и проекты',
        version: { number: 1, status: 'published' },
      },
    ],
    total: 1,
  });
  setup();
  await screen.findByText('Jira');

  fireEvent.change(screen.getByPlaceholderText('Поиск коллекций...'), {
    target: { value: 'проекты' },
  });
  expect(screen.getByRole('row', { name: /Jira/ })).toBeInTheDocument();
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
