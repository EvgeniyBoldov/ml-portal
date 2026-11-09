import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/shared/api/errors';
import { sandboxApi } from '../../api';
import { StoredResultCard } from './StoredResultCard';
import { resultCell } from './StoredResultModal';
import { ToolResponse } from './CallViews';

vi.mock('../../api', () => ({
  sandboxApi: { getResultMetadata: vi.fn(), getResultPage: vi.fn() },
}));

const metadata = {
  result_id: 'result',
  operation: 'search',
  row_count: 2,
  source_total: 3,
  source_complete: false,
  revision: 1,
  observed_schema: { name: { types: ['string'] } },
  expires_at: '2099-01-01T00:00:00Z',
};

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StoredResultCard sessionId="session" runId="run" resultId="result" />
    </QueryClientProvider>
  );
}

describe('StoredResultCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it('checks availability, displays schema and opens paginated data', async () => {
    vi.mocked(sandboxApi.getResultMetadata).mockResolvedValue(metadata);
    vi.mocked(sandboxApi.getResultPage).mockImplementation(
      async (_session, _run, _result, offset) => ({
        ...metadata,
        rows: [{ name: offset ? 'second' : 'first' }],
        offset,
        next_offset: offset ? null : 1,
      })
    );
    mount();
    const button = await screen.findByRole('button', {
      name: 'Показать результат в Store',
    });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.getByText('ID результата')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Показать схему' }));
    expect(screen.getByText('name')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    fireEvent.click(button);
    expect(await screen.findByText('first')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
    expect(await screen.findByText('second')).toBeInTheDocument();
    expect(sandboxApi.getResultPage).toHaveBeenLastCalledWith(
      'session',
      'run',
      'result',
      1,
      1
    );
  });

  it('shows stored counts and completeness once in the tool inspector', async () => {
    vi.mocked(sandboxApi.getResultMetadata).mockResolvedValue(metadata);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const call = {
      info: { status: 'completed' },
      requestView: { toolName: 'netbox_get_objects' },
      responseView: {
        toolResult: {
          success: true,
          data: { row_count: 2 },
          summary: 'Сохранено 2',
          truncated: true,
          resultId: 'result',
          delivery: 'stored',
          storedDescriptor: true,
          returnedCount: 2,
          sourceTotal: 3,
          sourceComplete: false,
          inlineComplete: false,
        },
      },
    };
    render(
      <QueryClientProvider client={client}>
        <ToolResponse call={call as never} sessionId="session" runId="run" />
      </QueryClientProvider>
    );
    await screen.findByRole('button', { name: 'Показать результат в Store' });
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByText('В наборе / в источнике')).toBeInTheDocument();
    expect(screen.queryByText('Данные для агента')).not.toBeInTheDocument();
    expect(screen.queryByText('Сохранено 2')).not.toBeInTheDocument();
  });

  it('does not claim that a missing result was definitely deleted', async () => {
    vi.mocked(sandboxApi.getResultMetadata).mockRejectedValue(
      new ApiError(404, 'not found')
    );
    mount();
    expect(
      await screen.findByText('Результат больше недоступен.')
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Показать результат в Store' })
    ).toBeDisabled();
  });

  it('distinguishes a service error from missing data', async () => {
    vi.mocked(sandboxApi.getResultMetadata).mockRejectedValue(
      new ApiError(503, 'unavailable')
    );
    mount();
    await waitFor(
      () =>
        expect(
          screen.getByText('Не удалось проверить доступность результата.')
        ).toBeInTheDocument(),
      { timeout: 3000 }
    );
    expect(
      screen.getByRole('button', { name: 'Повторить' })
    ).toBeInTheDocument();
  });

  it('reports a result that changed before reading and offers reload', async () => {
    vi.mocked(sandboxApi.getResultMetadata).mockResolvedValue(metadata);
    vi.mocked(sandboxApi.getResultPage).mockRejectedValue(
      new ApiError(409, 'changed')
    );
    mount();
    const button = screen.getByRole('button', { name: 'Показать результат в Store' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(
      await screen.findByText(
        'Результат изменился. Загрузите его с начала.',
        {},
        { timeout: 3000 }
      )
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Загрузить заново' })
    ).toBeInTheDocument();
  });

  it('reports a row that exceeds the page limit', async () => {
    vi.mocked(sandboxApi.getResultMetadata).mockResolvedValue(metadata);
    vi.mocked(sandboxApi.getResultPage).mockRejectedValue(
      new ApiError(413, 'too large')
    );
    mount();
    const button = screen.getByRole('button', { name: 'Показать результат в Store' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(
      await screen.findByText(
        'Строка 1 слишком велика для просмотра.',
        {},
        { timeout: 3000 }
      )
    ).toBeInTheDocument();
  });

  it('limits each cell to 300 Unicode characters and retains scalar values', () => {
    expect(resultCell('я'.repeat(300))).toHaveLength(300);
    expect(resultCell('😀'.repeat(301))).toBe(`${'😀'.repeat(300)}…`);
    expect(resultCell(false)).toBe('false');
    expect(resultCell(null)).toBe('null');
  });
});
