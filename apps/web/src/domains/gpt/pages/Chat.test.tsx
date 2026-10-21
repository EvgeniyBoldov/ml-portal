import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { ChatProvider } from '@/domains/chat/contexts/ChatContext';
import { uploadChatAttachment } from '@/shared/api/chats';
import { fetchStreamWithAuth } from '@/shared/api/streamAuth';
import Chat from './Chat';

vi.mock('@/domains/chat/components/ChatContextPanel', () => ({
  ChatContextPanel: () => null,
}));
vi.mock('@/shared/api/streamAuth', () => ({ fetchStreamWithAuth: vi.fn() }));
vi.mock('@/shared/api/chats', () => ({
  getChatUploadPolicy: vi
    .fn()
    .mockResolvedValue({ max_bytes: 10000, allowed_extensions: ['txt'] }),
  listMessages: vi
    .fn()
    .mockResolvedValue({ items: [], next_cursor: null, limit: 100 }),
  getPausedRun: vi.fn().mockResolvedValue({ pause: null }),
  generateChatTitle: vi.fn().mockResolvedValue({ generated: false }),
  uploadChatAttachment: vi.fn(),
}));

function Navigation() {
  const navigate = useNavigate();
  return (
    <button onClick={() => navigate('/gpt/chat/another')}>Другой чат</button>
  );
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={['/gpt/chat/chat']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ChatProvider>
          <Navigation />
          <Routes>
            <Route path="/gpt/chat/:chatId" element={<Chat />} />
          </Routes>
        </ChatProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function submitWithPendingUpload() {
  let resolveUpload!: (
    value: Awaited<ReturnType<typeof uploadChatAttachment>>
  ) => void;
  vi.mocked(uploadChatAttachment).mockImplementation(
    () =>
      new Promise(resolve => {
        resolveUpload = resolve;
      })
  );
  const view = setup();
  await waitFor(() =>
    expect(screen.queryByText('Загрузка истории…')).not.toBeInTheDocument()
  );
  fireEvent.change(view.container.querySelector('input[type=file]')!, {
    target: {
      files: [new File(['notes'], 'notes.txt', { type: 'text/plain' })],
    },
  });
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Проверь файл' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить сообщение' }));
  await waitFor(() => expect(uploadChatAttachment).toHaveBeenCalledOnce());
  const signal = vi.mocked(uploadChatAttachment).mock.calls[0][2]!;
  const finishUpload = () =>
    act(async () => {
      resolveUpload({
        artifact_id: 'file',
        file_name: 'notes.txt',
        file_ext: 'txt',
        size_bytes: 5,
        status: 'ready',
      });
    });
  return { signal, finishUpload };
}

beforeEach(() => {
  vi.clearAllMocks();
});

it('marks a partial response as stopped and keeps it out of subsequent streaming runs', async () => {
  let source!: ReadableStreamDefaultController<Uint8Array>;
  vi.mocked(fetchStreamWithAuth).mockImplementation(
    async (_path, options) =>
      new Response(
        new ReadableStream({
          start(controller) {
            source = controller;
            options.signal?.addEventListener('abort', () =>
              controller.error(new DOMException('Stopped', 'AbortError'))
            );
          },
        })
      )
  );
  setup();
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Вопрос' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить сообщение' }));
  await waitFor(() => expect(fetchStreamWithAuth).toHaveBeenCalledOnce());
  expect(vi.mocked(fetchStreamWithAuth).mock.calls[0][1].body).toEqual({
    content: 'Вопрос',
    artifact_ids: [],
  });
  act(() =>
    source.enqueue(
      new TextEncoder().encode('event: delta\ndata: Частичный ответ\n\n')
    )
  );
  await screen.findByText('Частичный ответ');
  fireEvent.click(screen.getByRole('button', { name: 'Остановить генерацию' }));
  await screen.findByText('Ответ остановлен');
  await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Следующий вопрос' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить сообщение' }));
  await waitFor(() => expect(fetchStreamWithAuth).toHaveBeenCalledTimes(2));
  expect(screen.getByText('Ответ остановлен')).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: 'Копировать сообщение' })
  ).toBeInTheDocument();
});

it('stops an attachment upload and restores the draft even if the upload responds after cancellation', async () => {
  const { signal, finishUpload } = await submitWithPendingUpload();
  fireEvent.click(screen.getByRole('button', { name: 'Остановить генерацию' }));
  expect(signal.aborted).toBe(true);
  await finishUpload();
  expect(fetchStreamWithAuth).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox')).toHaveValue('Проверь файл');
  expect(screen.getByText('notes.txt')).toBeInTheDocument();
});

it('does not submit an old upload or restore its draft into a different chat', async () => {
  const { signal, finishUpload } = await submitWithPendingUpload();
  fireEvent.click(screen.getByRole('button', { name: 'Другой чат' }));
  expect(signal.aborted).toBe(true);
  await finishUpload();
  expect(fetchStreamWithAuth).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox')).toHaveValue('');
  expect(screen.queryByText('notes.txt')).not.toBeInTheDocument();
});
