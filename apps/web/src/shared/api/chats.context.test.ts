import { getChatContext, resetChatContext } from './chats';

const apiRequestMock = vi.fn();

vi.mock('./http', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

describe('chat context API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads the bounded context inspection projection', async () => {
    apiRequestMock.mockResolvedValue({ revision: 3 });

    await getChatContext('chat-1');

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/context');
  });

  it('resets only the chat-local context through the typed endpoint', async () => {
    apiRequestMock.mockResolvedValue({ revision: 4, closed_items: 2 });

    await resetChatContext('chat-1');

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/context', {
      method: 'DELETE',
      idempotent: true,
    });
  });
});
