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
  getActiveChatRun,
  attachChatRun,
  resumeRunStream,
} from '@/shared/api/chats';

vi.mock('@/shared/api/streamAuth', () => ({ fetchStreamWithAuth: vi.fn() }));
vi.mock('@/shared/api/chats', () => ({
  listMessages: vi.fn(),
  generateChatTitle: vi.fn(),
  resumeRunStream: vi.fn(),
  getActiveChatRun: vi.fn(),
  attachChatRun: vi.fn(),
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
  it('loads the history tail without fetching every earlier page', async () => {
    const { result } = setup();
    vi.mocked(listMessages).mockResolvedValueOnce({
        items: [
          {
            id: 'message-99',
            chat_id: 'chat',
            role: 'user',
            content: 'Текст 99',
          },
          {
            id: 'latest',
            chat_id: 'chat',
            role: 'assistant',
            content: 'Самый свежий ответ',
          },
        ],
        next_cursor: null,
        previous_cursor: 'cursor-oldest',
        limit: 100,
      });
    await act(async () => {
      await result.current.actions.loadMessages('chat');
    });
    expect(listMessages).toHaveBeenCalledTimes(1);
    expect(listMessages).toHaveBeenCalledWith('chat', 100, undefined, { tail: true });
    expect(result.current.state.messagesByChat.chat.items).toHaveLength(2);
    expect(result.current.state.messagesByChat.chat.olderCursor).toBe('cursor-oldest');
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.content).toBe(
      'Самый свежий ответ'
    );
  });

  it('lets canonical history replace duplicate rows and keeps older pages', async () => {
    const { result } = setup();
    vi.mocked(listMessages).mockResolvedValueOnce({ items: [
      { id: 'older', chat_id: 'chat', role: 'user', content: 'старое' },
      { id: 'same', chat_id: 'chat', role: 'assistant', content: 'old' },
    ], next_cursor: null, limit: 100 });
    await act(async () => { await result.current.actions.loadMessages('chat'); });
    vi.mocked(listMessages).mockResolvedValueOnce({ items: [
      { id: 'same', chat_id: 'chat', role: 'assistant', content: 'canonical' },
    ], next_cursor: null, limit: 100 });
    await act(async () => { await result.current.actions.loadMessages('chat'); });
    expect(result.current.state.messagesByChat.chat.items.map(item => item.content)).toEqual(['старое', 'canonical']);
  });

  it('does not loop when loading the history tail', async () => {
    const { result } = setup();
    vi.mocked(listMessages).mockResolvedValue({
      items: [],
      next_cursor: 'same-cursor',
      limit: 100,
    });
    await act(async () => {
      await result.current.actions.loadMessages('chat');
    });
    expect(listMessages).toHaveBeenCalledTimes(1);
    expect(result.current.state.messagesByChat.chat.error).toBeUndefined();
    expect(result.current.state.messagesByChat.chat.loading).toBe(false);
  });

  it('works without crypto.randomUUID on an HTTP development origin', async () => {
    vi.stubGlobal('crypto', {});
    try {
      const { result } = setup();
      const source = stream();
      source.write('stage', {
        activity: {
          description: 'Ищу данные',
          run_id: 'run',
          stage: 'executing',
          action: 'intent',
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

  it('keeps one assistant anchor through repeated pause reloads and continuation', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(completedResponse('pause', pause));
    await act(async () => {
      await result.current.actions.sendMessageStream('chat', 'Запрос', vi.fn(), vi.fn());
    });
    vi.mocked(resumeRunStream).mockResolvedValue(completedResponse('pause', pause));
    await act(async () => {
      await result.current.actions.resumeStream('run-1', 'input', 'Первый', vi.fn(), vi.fn());
    });
    const anchorId = result.current.state.activeRun?.assistantMessageId;
    vi.mocked(listMessages).mockResolvedValue({ items: [
      { id: 'old-answer', chat_id: 'chat', role: 'assistant', content: 'Старый ответ' },
    ], next_cursor: null, limit: 100 });
    await act(async () => { await result.current.actions.loadMessages('chat'); });
    expect(result.current.state.messagesByChat.chat.items.some(item => item.id === anchorId)).toBe(true);
    const source = stream();
    vi.mocked(resumeRunStream).mockResolvedValue(source.response);
    let continuation: Promise<boolean>;
    act(() => {
      continuation = result.current.actions.resumeStream('run-1', 'input', 'Второй', vi.fn(), vi.fn());
    });
    await act(async () => { source.write('delta', 'Продолжение'); });
    await waitFor(() => expect(result.current.state.messagesByChat.chat.items.find(item => item.id === anchorId)?.content).toBe('Продолжение'));
    await act(async () => {
      source.write('pause', pause);
      source.close();
      await continuation;
    });
    expect(result.current.state.messagesByChat.chat.items.filter(item => item.id === anchorId)).toHaveLength(1);
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

  it('clears a terminal startup failure pause and allows a fresh message', async () => {
    const { result } = setup();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(completedResponse('pause', pause));
    await act(async () => {
      await result.current.actions.sendMessageStream('chat', 'Запрос', vi.fn(), vi.fn());
    });
    vi.mocked(listMessages).mockResolvedValue({ items: [
      { id: 'user-1', chat_id: 'chat', role: 'user', content: 'Запрос' },
    ], next_cursor: null, limit: 100 });
    const message = 'Не удалось продолжить выполнение. Отправьте запрос заново.';
    vi.mocked(resumeRunStream).mockResolvedValue(new Response(JSON.stringify({
      type: 'about:blank', status: 503, title: message, detail: message,
      code: 'CHAT_RUNTIME_START_FAILED', details: { run_id: 'run-1', status: 'failed' },
    }), { status: 503, headers: { 'Content-Type': 'application/problem+json' } }));
    const onError = vi.fn();

    await act(async () => {
      expect(await result.current.actions.resumeStream('run-1', 'input', 'Ответ', vi.fn(), onError)).toBe(false);
    });

    expect(onError).toHaveBeenCalledWith(message);
    expect(result.current.state.pausedRunId).toBeNull();
    expect(result.current.state.pendingInput).toBeNull();
    expect(result.current.state.pendingConfirmations).toEqual([]);
    expect(result.current.state.activeRun).toBeNull();
    expect(result.current.state.isStreaming).toBe(false);
    expect(result.current.state.messagesByChat.chat.items.map(item => item.id)).toEqual(['user-1']);
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(completedResponse('final', {
      message_id: 'new-answer', content: 'Новый ответ',
    }));
    await act(async () => {
      expect(await result.current.actions.sendMessageStream('chat', 'Новый запрос', vi.fn(), vi.fn())).toBe(true);
    });
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.content).toBe('Новый ответ');
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
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.outcome).toBe(
      'interrupted'
    );
    expect(result.current.state.isStreaming).toBe(false);
  });

  it('blocks a duplicate send and detaches the observer without marking cancellation', async () => {
    const { result } = setup();
    const source = stream();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
    const onError = vi.fn();
    let pending: Promise<boolean>;
    act(() => {
      pending = result.current.actions.sendMessageStream(
        'chat',
        'Запрос',
        vi.fn(),
        vi.fn()
      );
    });
    await act(async () => {
      source.write('delta', 'Последние символы');
      await result.current.actions.sendMessageStream(
        'chat',
        'Дубль',
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
    expect(result.current.state.messagesByChat.chat.items.at(-1)?.outcome).toBeUndefined();
    expect(result.current.state.activeRun).toBeNull();
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

  it('keeps a new optimistic answer when an older page resolves before stream events', async () => {
    const { result } = setup();
    vi.mocked(listMessages).mockResolvedValueOnce({ items: [
      { id: 'old-answer', chat_id: 'chat', role: 'assistant', content: 'Предыдущий ответ' },
    ], next_cursor: null, limit: 100 });
    await act(async () => { await result.current.actions.loadMessages('chat'); });
    let resolveHistory!: (value: Awaited<ReturnType<typeof listMessages>>) => void;
    vi.mocked(listMessages).mockImplementationOnce(() => new Promise(resolve => { resolveHistory = resolve; }));
    let history!: Promise<void>;
    act(() => { history = result.current.actions.loadMessages('chat'); });
    await waitFor(() => expect(listMessages).toHaveBeenCalledTimes(2));
    const source = stream();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
    let send!: Promise<boolean>;
    act(() => { send = result.current.actions.sendMessageStream('chat', 'новый вопрос', vi.fn(), vi.fn()); });
    const assistantId = result.current.state.activeRun?.assistantMessageId;
    await act(async () => {
      resolveHistory({ items: [{ id: 'old-answer', chat_id: 'chat', role: 'assistant', content: 'Канонический старый ответ' }], next_cursor: null, limit: 100 });
      await history;
    });
    expect(result.current.state.messagesByChat.chat.items.some(item => item.id === assistantId)).toBe(true);
    await act(async () => {
      source.write('delta', 'Новый ответ');
      source.write('final', { message_id: 'new-answer', content: 'Новый ответ' });
      source.close();
      await send;
    });
    expect(result.current.state.messagesByChat.chat.items.find(item => item.id === 'new-answer')?.content).toBe('Новый ответ');
  });

  it('keeps active-run restoration stable while stream progress updates', async () => {
    const { result } = setup();
    const loadActiveRun = result.current.actions.loadActiveRun;
    const source = stream();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
    let send!: Promise<boolean>;
    act(() => { send = result.current.actions.sendMessageStream('chat', 'Запрос', vi.fn(), vi.fn()); });
    await act(async () => {
      source.write('stage', { activity: { run_id: 'run', stage: 'executing', action: 'intent', description: 'Ищу' } });
    });
    expect(result.current.actions.loadActiveRun).toBe(loadActiveRun);
    act(() => { result.current.actions.abortStream(); });
    await act(async () => { source.close(); await send; });
  });

  it('ignores delayed active-run restoration after navigation and a new send', async () => {
    const { result } = setup();
    let resolveRun: (value: Awaited<ReturnType<typeof getActiveChatRun>>) => void;
    vi.mocked(getActiveChatRun).mockImplementation(() => new Promise(resolve => { resolveRun = resolve; }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], next_cursor: null, limit: 100 });
    act(() => { result.current.actions.setCurrentChat('chat-a'); });
    let restore: Promise<void>;
    act(() => { restore = result.current.actions.loadActiveRun('chat-a'); });
    await waitFor(() => expect(getActiveChatRun).toHaveBeenCalledWith('chat-a'));
    act(() => { result.current.actions.setCurrentChat('chat-b'); });
    const source = stream();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
    let send: Promise<boolean>;
    act(() => { send = result.current.actions.sendMessageStream('chat-b', 'новый', vi.fn(), vi.fn()); });
    await act(async () => {
      resolveRun({ run: { run_id: 'old-run', user_message_id: 'old-user', turn_id: 'turn-old', status: 'running' } });
      await restore;
    });
    expect(attachChatRun).not.toHaveBeenCalled();
    expect(result.current.state.activeRun?.userMessageId).not.toBe('old-user');
    act(() => { result.current.actions.abortStream(); });
    await act(async () => { source.close(); await send; });
  });

  it('ignores a delayed active-run lookup when a send starts in the same chat', async () => {
    const { result } = setup();
    let resolveRun!: (value: Awaited<ReturnType<typeof getActiveChatRun>>) => void;
    vi.mocked(getActiveChatRun).mockImplementation(() => new Promise(resolve => { resolveRun = resolve; }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], next_cursor: null, limit: 100 });
    act(() => { result.current.actions.setCurrentChat('chat'); });
    let restore!: Promise<void>;
    act(() => { restore = result.current.actions.loadActiveRun('chat'); });
    await waitFor(() => expect(getActiveChatRun).toHaveBeenCalledWith('chat'));
    const source = stream();
    vi.mocked(fetchStreamWithAuth).mockResolvedValue(source.response);
    let send!: Promise<boolean>;
    act(() => { send = result.current.actions.sendMessageStream('chat', 'новый запрос', vi.fn(), vi.fn()); });
    await act(async () => {
      resolveRun({ run: { run_id: 'old-run', user_message_id: 'old-user', turn_id: 'turn-old', status: 'running' } });
      await restore;
    });
    expect(attachChatRun).not.toHaveBeenCalled();
    expect(result.current.state.activeRun?.userMessageId).not.toBe('old-user');
    act(() => { result.current.actions.abortStream(); });
    await act(async () => { source.close(); await send; });
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
