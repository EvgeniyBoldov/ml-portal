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
import { memoryScopesApi } from '@/shared/api/memoryScopes';
import CollectionDataPage from './CollectionDataPage';

vi.mock('@shared/ui/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));
vi.mock('@shared/lib/sse', () => {
  class MockSSEClient {
    static clients: Array<{
      onMessage: (
        events: Array<{ type: string; data: unknown; timestamp: number }>
      ) => void;
    }> = [];
    constructor(options: {
      onMessage: (
        events: Array<{ type: string; data: unknown; timestamp: number }>
      ) => void;
    }) {
      MockSSEClient.clients.push(options);
    }
    connect = vi.fn();
    disconnect = vi.fn();
  }
  return {
    SSEClient: MockSSEClient,
    getSseClients: () => MockSSEClient.clients,
    openSSE: () => ({ disconnect: vi.fn() }),
  };
});
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
function setup(
  type: Collection['collection_type'],
  detailError?: Error,
  detailData?: Collection
) {
  const detail = vi.spyOn(collectionsApi, 'getBySlug');
  if (detailError) detail.mockRejectedValue(detailError);
  else detail.mockResolvedValue(detailData ?? collection(type));
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

it.each(['api', 'sql'] as const)(
  'shows external %s metadata without requesting collection content',
  async type => {
    const getData = vi.spyOn(collectionsApi, 'getData').mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    const external = {
      ...collection(type),
      name: 'Jira',
      slug: 'jira',
      data_instance: {
        id: 'jira-source',
        slug: 'jira-prod',
        name: 'Jira Prod',
      },
      source: { name: 'Jira Prod', type },
      description: 'Задачи и проекты Jira',
      purpose: 'Поиск сведений по задачам',
      version: { number: 3, status: 'published' as const },
      count: { value: null, kind: null, unit: null },
    };
    setup(type, undefined, external);

    expect(
      await screen.findByRole('heading', { name: 'Jira' })
    ).toBeInTheDocument();
    expect(screen.getAllByText('Jira Prod').length).toBeGreaterThan(0);
    expect(screen.getByText('Задачи и проекты Jira')).toBeInTheDocument();
    expect(screen.getByText('Версия 3')).toBeInTheDocument();
    expect(screen.getByText('Количество не указано')).toBeInTheDocument();
    expect(
      screen.getByText(/Просмотр содержимого внешнего источника/)
    ).toBeInTheDocument();
    expect(getData).not.toHaveBeenCalled();
  }
);

it('does not show unpublished version metadata on an external collection page', async () => {
  setup('api', undefined, {
    ...collection('api'),
    description: 'Описание черновика',
    purpose: 'Назначение черновика',
    version: null,
    count: { value: null, kind: null, unit: null },
  });

  expect(await screen.findByText('Описание не задано')).toBeInTheDocument();
  expect(screen.queryByText('Описание черновика')).not.toBeInTheDocument();
  expect(screen.queryByText('Назначение черновика')).not.toBeInTheDocument();
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

it('refreshes aggregate counts after a collection SSE snapshot', async () => {
  const listDocuments = vi
    .spyOn(collectionsApi, 'listDocuments')
    .mockResolvedValueOnce({
      items: [doc('document-1')],
      total: 1,
      page: 1,
      size: 50,
      has_more: false,
      stats: {
        total: 1,
        ready: 1,
        processing: 0,
        partial: 0,
        failed: 0,
        uploaded: 0,
        archived: 0,
      },
    })
    .mockResolvedValue({
      items: [{ ...doc('document-1'), agg_status: 'partial' }],
      total: 1,
      page: 1,
      size: 50,
      has_more: false,
      stats: {
        total: 1,
        ready: 0,
        processing: 0,
        partial: 1,
        failed: 0,
        uploaded: 0,
        archived: 0,
      },
    });
  setup('document');
  await screen.findByText('document-1');
  await waitFor(() => expect(listDocuments).toHaveBeenCalledTimes(1));

  const sseModule = (await import('@shared/lib/sse')) as unknown as {
    getSseClients: () => Array<{
      onMessage: (
        events: Array<{ type: string; data: unknown; timestamp: number }>
      ) => void;
    }>;
  };
  const client = sseModule.getSseClients().at(-1);
  expect(client).toBeDefined();
  client?.onMessage([
    {
      type: 'rag.snapshot',
      data: { items: [{ document_id: 'document-1', agg_status: 'partial' }] },
      timestamp: Date.now(),
    },
  ]);

  await waitFor(() => expect(listDocuments).toHaveBeenCalledTimes(2));
  expect(
    screen.getByRole('button', { name: /1 Частично готово/i })
  ).toBeInTheDocument();
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

it('shows separate RAG and LongMemory readiness metrics, project membership, and row-menu delete', async () => {
  const target = {
    ...doc('network-guide'),
    name: 'Руководство сети',
    filename: 'network-guide.pdf',
    size_bytes: 1_572_864,
    artifacts: { chunks: { key: 'documents/chunks.ndjson', chunk_count: 42 } },
    memory: {
      policy: 'explicit' as const,
      enabled: true,
      effective_enabled: true,
      project_keys: [],
      scope_keys: ['network'],
      extraction_status: 'completed',
      extraction_metrics: {
        status: 'completed',
        steps: {
          extract: {
            status: 'completed',
            metrics: {
              passages: 8,
              entities: 12,
              facts: 7,
              extracted_triples: 9,
            },
          },
          index: { status: 'running', metrics: { scope_edges: 5 } },
        },
      },
    },
  } satisfies CollectionDocument;
  vi.spyOn(collectionsApi, 'listDocuments').mockResolvedValue({
    items: [target],
    total: 1,
    page: 1,
    size: 50,
    has_more: false,
  });
  vi.spyOn(memoryScopesApi, 'list').mockResolvedValue([
    {
      id: 'scope-1',
      scope_type: 'project',
      key: 'network',
      name: 'Сеть',
      aliases: [],
      is_all: false,
    },
  ]);
  const remove = vi.spyOn(collectionsApi, 'deleteDocuments').mockResolvedValue({
    deleted: 1,
    collection_id: 'collection-id',
  });
  vi.spyOn(window, 'confirm').mockReturnValue(true);

  setup('document');

  expect(await screen.findByText('Руководство сети')).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'RAG' })).toBeInTheDocument();
  expect(
    screen.getByRole('columnheader', { name: 'LongMemory' })
  ).toBeInTheDocument();
  expect(
    screen.queryByRole('columnheader', { name: 'Действия' })
  ).not.toBeInTheDocument();
  expect(screen.getByText('42 чанков')).toBeInTheDocument();
  expect(screen.getByText('Индексируется')).toBeInTheDocument();
  expect(
    screen.getByText(/9 триплетов · 7 фактов · 8 фрагм\./)
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Индекс: выполняется · Граф области: 5 связей/)
  ).toBeInTheDocument();
  expect(screen.getByText('Сеть')).toBeInTheDocument();
  expect(
    screen.queryByText(/наследуется|Semantic Memory|семантическая память/i)
  ).not.toBeInTheDocument();

  fireEvent.click(
    screen.getByRole('button', { name: 'Действия для Руководство сети' })
  );
  fireEvent.click(
    await screen.findByRole('menuitem', { name: 'Удалить документ' })
  );
  await waitFor(() =>
    expect(remove).toHaveBeenCalledWith('collection-id', ['network-guide'])
  );
});

it('does not call LongMemory ready when indexing is not confirmed', async () => {
  const target: CollectionDocument = {
    ...doc('incomplete-memory'),
    memory: {
      policy: 'explicit',
      enabled: true,
      effective_enabled: true,
      project_keys: [],
      scope_keys: [],
      extraction_status: 'completed',
      extraction_metrics: {
        status: 'completed',
        steps: {
          extract: { status: 'completed', metrics: { extracted_triples: 2 } },
        },
      },
    },
  };
  vi.spyOn(collectionsApi, 'listDocuments').mockResolvedValue({
    items: [target],
    total: 1,
    page: 1,
    size: 50,
    has_more: false,
  });

  setup('document');

  expect(
    await screen.findByText('Готовность не подтверждена')
  ).toBeInTheDocument();
  expect(screen.queryByText('Готова')).not.toBeInTheDocument();
});

it('distinguishes disabled, queued, extracting, ready, and failed LongMemory states', async () => {
  const memory = (
    extractionStatus: string,
    enabled: boolean,
    extractStage: string,
    indexStage: string
  ): NonNullable<CollectionDocument['memory']> => ({
    policy: 'explicit',
    enabled,
    effective_enabled: enabled,
    project_keys: [],
    scope_keys: [],
    extraction_status: extractionStatus,
    extraction_metrics: {
      steps: {
        extract: { status: extractStage, metrics: {} },
        index: { status: indexStage, metrics: {} },
      },
    },
  });
  const items: CollectionDocument[] = [
    {
      ...doc('disabled'),
      memory: memory('completed', false, 'completed', 'completed'),
    },
    { ...doc('queued'), memory: memory('queued', true, 'queued', 'queued') },
    {
      ...doc('extracting'),
      memory: memory('running', true, 'running', 'queued'),
    },
    {
      ...doc('ready'),
      memory: memory('completed', true, 'completed', 'completed'),
    },
    {
      ...doc('extract-error'),
      memory: memory('failed', true, 'failed', 'queued'),
    },
    {
      ...doc('index-error'),
      memory: memory('failed', true, 'completed', 'failed'),
    },
  ];
  vi.spyOn(collectionsApi, 'listDocuments').mockResolvedValue({
    items,
    total: items.length,
    page: 1,
    size: 50,
    has_more: false,
  });

  setup('document');

  expect(await screen.findByText('disabled')).toBeInTheDocument();
  expect(screen.getByText('Отключена')).toBeInTheDocument();
  expect(screen.getByText('Ожидает обработки')).toBeInTheDocument();
  expect(screen.getByText('Извлекается')).toBeInTheDocument();
  expect(screen.getByText('Готова')).toBeInTheDocument();
  expect(screen.getByText('Ошибка извлечения')).toBeInTheDocument();
  expect(screen.getByText('Ошибка индексации')).toBeInTheDocument();
});
