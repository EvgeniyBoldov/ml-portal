import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ChatProvider,
  useChatActions,
  useChatMessagesState,
} from './ChatContext';
import { fetchStreamWithAuth } from '@/shared/api/streamAuth';
import {
  generateChatTitle,
  listMessages,
  resumeRunStream,
} from '@/shared/api/chats';

vi.mock('@shared/api/hooks/useChats', () => ({
  useChats: () => ({ data: { items: [] } }),
}));
vi.mock('@/shared/api/streamAuth', () => ({ fetchStreamWithAuth: vi.fn() }));
vi.mock('@/shared/api/chats', () => ({
  listMessages: vi.fn(),
  generateChatTitle: vi.fn(),
  resumeRunStream: vi.fn(),
  getPausedRun: vi.fn(),
}));

function stream() {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const response = new Response(
    new ReadableStream<Uint8Array>({
      start(value) {
        controller = value;
      },
    })
  );
  return {
    response,
    write: (event: string, data: unknown) =>
      controller.enqueue(
        new TextEncoder().encode(
          `event: ${event}\ndata: ${typeof data === 'string' ? data : JSON.stringify(data)}\n\n`
        )
      ),
    close: () => controller.close(),
  };
}
function completedResponse(event: string, data: unknown) {
  const source = stream();
  source.write(event, data);
  source.close();
  return source.response;
}
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <ChatProvider>{children}</ChatProvider>
    </QueryClientProvider>
  );
  return renderHook(
    () => ({ actions: useChatActions(), state: useChatMessagesState() }),
    { wrapper }
  );
}
const pause = {
  run_id: 'run-1',
  reason: 'waiting_input',
  context: { question: 'Какой проект?' },
  action: {},
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(generateChatTitle).mockResolvedValue({
    generated: false,
    title: null,
  });
});

describe('chat streaming', () => {
  it('works without crypto.randomUUID on an HTTP development origin', async () => {
    vi.stubGlobal('crypto', {});
    try {
      const { result } = setup();
      const source = stream();
      source.write('status', {
        stage: 'runtime_progress',
        progress: {
          description: 'Ищу данные',
          run_id: 'run',
          phase: 'execution',
          kind: 'intent',
        },
      });
      source.write('final', { message_id: 'answer', content: 'Ответ' });
      source.close();
      vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
      const onError = vi.fn();
      await act(async () => {
        await result.current.actions.sendMessageStream(
          'chat',
          'Запрос',
          false,
          vi.fn(),
          onError
        );
      });
      expect(onError).not.toHaveBeenCalled();
      expect(result.current.state.messagesByChat.chat.items.at(-1)?.id).toBe(
        'answer'
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('streams a resumed answer immediately and replaces it with the final message', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(
      completedResponse('pause', pause)
    );
    await act(async () => {
      await result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
    });
    expect(result.current.state.pendingInput?.question).toBe('Какой проект?');
    const source = stream();
    vi.mocked(resumeRunStream).mockResolvedValue(source.response);
    let continuation: Promise<boolean>;
    act(() => {
      continuation = result.current.actions.resumeStream(
        'run-1',
        'input',
        'Первый',
        vi.fn(),
        vi.fn()
      );
    });
    await act(async () => {
      source.write('delta', 'Ищу данные');
    });
    await waitFor(() =>
      expect(
        result.current.state.messagesByChat.chat.items.at(-1)?.content
      ).toBe('Ищу данные')
    );
    expect(result.current.state.isStreaming).toBe(true);
    expect(result.current.state.pendingInput).toBeNull();
    await act(async () => {
      source.write('final', {
        message_id: 'answer',
        content: 'Готовый ответ',
        attachments: [{ artifact_id: 'file', file_name: 'report.csv' }],
      });
      source.close();
      expect(await continuation).toBe(true);
    });
    expect(result.current.state.messagesByChat.chat.items.at(-1)).toMatchObject(
      {
        id: 'answer',
        content: 'Готовый ответ',
        isOptimistic: false,
        meta: { attachments: [{ artifactId: 'file', fileName: 'report.csv' }] },
      }
    );
    expect(result.current.state.activeRun).toBeNull();
    expect(result.current.state.isStreaming).toBe(false);
  });

  it('retains another pause received during continuation', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(
      completedResponse('pause', pause)
    );
    await act(async () => {
      await result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
    });
    vi.mocked(resumeRunStream).mockResolvedValue(
      completedResponse('pause', {
        ...pause,
        context: { question: 'Какой период?' },
      })
    );
    await act(async () => {
      expect(
        await result.current.actions.resumeStream(
          'run-1',
          'input',
          'Первый',
          vi.fn(),
          vi.fn()
        )
      ).toBe(true);
    });
    expect(result.current.state.pendingInput?.question).toBe('Какой период?');
    expect(result.current.state.activeRun?.status).toBe('waiting_input');
  });

  it('keeps a rejected continuation available to retry', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(
      completedResponse('pause', pause)
    );
    await act(async () => {
      await result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
    });
    vi.mocked(resumeRunStream).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Уже выполняется' }), {
        status: 409,
      })
    );
    const onError = vi.fn();
    await act(async () => {
      expect(
        await result.current.actions.resumeStream(
          'run-1',
          'input',
          'Первый',
          vi.fn(),
          onError
        )
      ).toBe(false);
    });
    expect(onError).toHaveBeenCalledWith('Уже выполняется');
    expect(result.current.state.pausedRunId).toBe('run-1');
    expect(result.current.state.pendingInput?.question).toBe('Какой проект?');
    expect(result.current.state.activeRun?.status).toBe('waiting_input');
  });

  it('keeps partial text on unexpected EOF and reports interruption', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(
      completedResponse('delta', 'Начало ответа')
    );
    const onError = vi.fn();
    await act(async () => {
      await result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        onError
      );
    });
    expect(onError).toHaveBeenCalledWith(
      expect.stringContaining('Соединение прервалось')
    );
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.content).toBe(
      'Начало ответа'
    );
    expect(result.current.state.isStreaming).toBe(false);
  });

  it('blocks a duplicate send and preserves buffered text when stopped', async () => {
    const { result } = setup();
    const source = stream();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
    const onError = vi.fn();
    let pending: Promise<boolean>;
    act(() => {
      pending = result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
    });
    await act(async () => {
      source.write('delta', 'Последние символы');
      await result.current.actions.sendMessageStream(
        'chat',
        'Дубль',
        false,
        vi.fn(),
        onError
      );
    });
    act(() => {
      result.current.actions.abortStream();
    });
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.content).toBe(
      'Последние символы'
    );
    expect(vi.mocked(fetchStreamWithAuth)).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(
      'Дождитесь завершения текущего ответа'
    );
    await act(async () => {
      source.close();
      await pending;
    });
  });

  it('ignores a response from a chat that has been left', async () => {
    const { result } = setup();
    let resolve: (response: Response) => void;
    vi.mocked(fetchStreamWithAuth).mockImplementation(
      () =>
        new Promise(value => {
          resolve = value;
        })
    );
    let pending: Promise<boolean>;
    act(() => {
      pending = result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
    });
    act(() => {
      result.current.actions.setCurrentChat('another');
    });
    await act(async () => {
      resolve(completedResponse('pause', pause));
      await pending;
    });
    expect(result.current.state.pendingInput).toBeNull();
    expect(result.current.state.activeRun).toBeNull();
  });

  it('does not let an older history load overwrite a streamed answer', async () => {
    const { result } = setup();
    let resolve: (value: Awaited<ReturnType<typeof listMessages>>) => void;
    vi.mocked(listMessages).mockImplementation(
      () =>
        new Promise(value => {
          resolve = value;
        })
    );
    let history: Promise<void>;
    act(() => {
      history = result.current.actions.loadMessages('chat');
    });
    await waitFor(() => expect(listMessages).toHaveBeenCalled());
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(
      completedResponse('final', { message_id: 'answer', content: 'Ответ' })
    );
    await act(async () => {
      await result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
      resolve({
        items: [
          { id: 'older', chat_id: 'chat', role: 'assistant', content: 'Ранее' },
        ],
        next_cursor: null,
        limit: 100,
      });
      await history;
    });
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.content).toBe(
      'Ответ'
    );
    expect(result.current.state.messagesByChat.chat.items[0]?.content).toBe(
      'Ранее'
    );
    vi.mocked(listMessages).mockRejectedValue(new Error('network'));
    await act(async () => {
      await result.current.actions.loadMessages('chat');
    });
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.content).toBe(
      'Ответ'
    );
  });

  it('replaces optimistic placeholders when a cached answer reloads persisted history', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(
      completedResponse('cached', {
        user_message_id: 'user',
        assistant_message_id: 'answer',
      })
    );
    vi.mocked(listMessages).mockResolvedValue({
      items: [
        { id: 'user', chat_id: 'chat', role: 'user', content: 'Запрос' },
        {
          id: 'answer',
          chat_id: 'chat',
          role: 'assistant',
          content: 'Сохранённый ответ',
        },
      ],
      next_cursor: null,
      limit: 100,
    });
    await act(async () => {
      await result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        false,
        vi.fn(),
        vi.fn()
      );
    });
    expect(
      result.current.state.messagesByChat.chat.items.map(item => item.id)
    ).toEqual(['user', 'answer']);
    expect(result.current.state.activeRun).toBeNull();
  });
});
