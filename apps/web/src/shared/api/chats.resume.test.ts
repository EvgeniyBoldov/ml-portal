import { resumeRunStream } from './chats';

const fetchStreamWithAuthMock = vi.fn();

vi.mock('@/shared/api/streamAuth', () => ({
  fetchStreamWithAuth: (...args: unknown[]) => fetchStreamWithAuthMock(...args),
}));

describe('resumeRunStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchStreamWithAuthMock.mockResolvedValue(new Response());
  });

  it('sends input only for clarification answers', async () => {
    await resumeRunStream('run-1', 'input', '  Название проекта  ');

    expect(fetchStreamWithAuthMock).toHaveBeenCalledWith(
      '/chats/runs/run-1/resume',
      {
        body: { action: 'input', input: '  Название проекта  ' },
        signal: undefined,
      }
    );
  });

  it.each(['confirm', 'cancel'] as const)(
    'sends a valid %s action without an input field',
    async action => {
      await resumeRunStream('run-1', action, 'must not be sent');

      expect(fetchStreamWithAuthMock).toHaveBeenCalledWith(
        '/chats/runs/run-1/resume',
        {
          body: { action },
          signal: undefined,
        }
      );
    }
  );
});
