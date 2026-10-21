import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import {
  collectionsApi,
  type Collection,
  type CollectionDocument,
} from '@/shared/api/collections';
import CollectionDataPage from './CollectionDataPage';

vi.mock('@shared/ui/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));
vi.mock('@shared/lib/sse', () => ({
  SSEClient: class {
    connect = vi.fn();
    disconnect = vi.fn();
  },
  openSSE: () => ({ disconnect: vi.fn() }),
}));
vi.mock('@/shared/api/http', () => ({
  apiRequest: vi.fn(async (path: string) =>
    path === '/memory/scopes' ? [] : {}
  ),
}));

function collection(type: Collection['collection_type']): Collection {
  return {
    id: 'collection-id',
    slug: 'orders',
    name: 'Заказы',
    collection_type: type,
    fields: [
      {
        name: 'name',
        required: true,
        data_type: 'string',
        search_modes: ['like'],
      },
    ],
    data_instance_id: 'instance',
    has_vector_search: false,
    total_rows: 101,
    vectorized_rows: 0,
    total_chunks: 0,
    failed_rows: 0,
    vectorization_progress: 0,
    is_fully_vectorized: false,
    is_active: true,
    created_at: '',
    updated_at: '',
  };
}
function setup(type: Collection['collection_type'], detailError?: Error) {
  const detail = vi.spyOn(collectionsApi, 'getBySlug');
  if (detailError) detail.mockRejectedValue(detailError);
  else detail.mockResolvedValue(collection(type));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={['/gpt/collections/orders']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/gpt/collections/:slug"
            element={<CollectionDataPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...view, client };
}
const doc = (id: string): CollectionDocument => ({
  id,
  name: id,
  filename: id,
  status: 'ready',
  agg_status: 'ready',
  scope: 'tenant',
  tags: [],
  size_bytes: 1,
  content_type: 'text/plain',
  created_at: null,
  updated_at: null,
  collection_row_id: null,
  title: null,
  source: null,
  doc_scope: null,
  s3_key: null,
  meta_fields: {},
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it('refetches table data when the search changes on the first page', async () => {
  const getData = vi.spyOn(collectionsApi, 'getData').mockResolvedValue({
    items: [{ id: 'row', name: 'Запись' }],
    total: 1,
    limit: 50,
    offset: 0,
  });
  setup('table');
  await screen.findByText('Запись');
  fireEvent.change(screen.getByPlaceholderText('Поиск...'), {
    target: { value: 'needle' },
  });
  await waitFor(() =>
    expect(getData).toHaveBeenCalledWith(
      'orders',
      expect.objectContaining({ search: 'needle' })
    )
  );
});

it.each(['document', 'template'] as const)(
  'keeps the selected %s page while its request is pending',
  async type => {
    let resolvePage!: () => void;
    if (type === 'document') {
      vi.spyOn(collectionsApi, 'listDocuments').mockImplementation(
        async (_id, params) =>
          params?.page === 2
            ? new Promise(resolve => {
                resolvePage = () =>
                  resolve({
                    items: [doc('Вторая страница')],
                    total: 101,
                    page: 2,
                    size: 50,
                    has_more: true,
                  });
              })
            : {
                items: [doc('Первая страница')],
                total: 101,
                page: 1,
                size: 50,
                has_more: true,
              }
      );
    } else {
      vi.spyOn(collectionsApi, 'listTemplates').mockImplementation(
        async (_id, params) =>
          params?.page === 2
            ? new Promise(resolve => {
                resolvePage = () =>
                  resolve({
                    items: [{ id: 'second', title: 'Вторая страница' }],
                    total: 101,
                    page: 2,
                    size: 50,
                  });
              })
            : {
                items: [{ id: 'first', title: 'Первая страница' }],
                total: 101,
                page: 1,
                size: 50,
              }
      );
    }
    setup(type);
    await screen.findByText('Первая страница');
    fireEvent.click(screen.getByRole('button', { name: 'Следующая страница' }));
    await waitFor(() => expect(resolvePage).toBeDefined());
    // Keep the response pending beyond the search debounce interval: opening a
    // collection must not schedule an unrelated reset back to its first page.
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 350));
    });
    await act(async () => {
      resolvePage();
    });
    await screen.findByText('Вторая страница');
    expect(screen.getByText('Страница 2 из 3')).toBeInTheDocument();
  }
);

it.each(['table', 'document', 'template'] as const)(
  'shows a retry action for failed %s loading instead of an empty collection',
  async type => {
    const failure = new Error('Network failure');
    if (type === 'table')
      vi.spyOn(collectionsApi, 'getData').mockRejectedValue(failure);
    if (type === 'document')
      vi.spyOn(collectionsApi, 'listDocuments').mockRejectedValue(failure);
    if (type === 'template')
      vi.spyOn(collectionsApi, 'listTemplates').mockRejectedValue(failure);
    setup(type);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось загрузить'
    );
    expect(
      screen.getByRole('button', { name: 'Повторить' })
    ).toBeInTheDocument();
  }
);

it('does not report an unavailable API as a missing collection', async () => {
  setup('table', new Error('Service unavailable'));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Не удалось загрузить'
  );
  expect(screen.queryByText('Коллекция не найдена')).not.toBeInTheDocument();
});

it.each(['completed', 'running'])(
  'stops HippoRAG polling after an initially %s operation completes',
  async initialStatus => {
    vi.useFakeTimers();
    const terminalDoc = {
      ...doc('Готовый документ'),
      memory: {
        policy: 'collection' as const,
        enabled: null,
        effective_enabled: true,
        project_keys: [],
        scope_keys: ['company'],
        extraction_status: 'completed',
        extraction_metrics: {},
      },
    };
    const page = {
      items: [terminalDoc],
      total: 1,
      page: 1,
      size: 50,
      has_more: false,
    };
    const list = vi
      .spyOn(collectionsApi, 'listDocuments')
      .mockResolvedValueOnce({
        ...page,
        items: [
          {
            ...terminalDoc,
            memory: { ...terminalDoc.memory, extraction_status: initialStatus },
          },
        ],
      })
      .mockResolvedValue(page);
    const { client } = setup('document');
    for (let i = 0; i < 3; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
    }
    expect(screen.getByText('Готовый документ')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(list).toHaveBeenCalledTimes(initialStatus === 'completed' ? 1 : 2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(list).toHaveBeenCalledTimes(initialStatus === 'completed' ? 1 : 2);
    client.clear();
  }
);
