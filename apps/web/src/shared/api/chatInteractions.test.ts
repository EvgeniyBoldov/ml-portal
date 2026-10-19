import { resumeRunStream } from './chats';
import { fetchStreamWithAuth } from './streamAuth';

vi.mock('./streamAuth', () => ({
  fetchStreamWithAuth: vi.fn().mockResolvedValue(new Response()),
}));

describe('typed interaction responses', () => {
  it.each(['Проект Альфа', true, false])(
    'sends the original JSON response value %s',
    async response => {
      await resumeRunStream(
        'run',
        'answer',
        response,
        undefined,
        'question-id',
        true
      );
      expect(fetchStreamWithAuth).toHaveBeenLastCalledWith(
        '/chats/runs/run/resume',
        expect.objectContaining({
          body: { action: 'answer', response, pause_id: 'question-id' },
        })
      );
    }
  );

  it('keeps cancellation distinct from a negative answer', async () => {
    await resumeRunStream('run', 'cancel', '', undefined, 'question-id', true);
    expect(fetchStreamWithAuth).toHaveBeenLastCalledWith(
      '/chats/runs/run/resume',
      expect.objectContaining({
        body: { action: 'cancel', pause_id: 'question-id' },
      })
    );
  });
});
