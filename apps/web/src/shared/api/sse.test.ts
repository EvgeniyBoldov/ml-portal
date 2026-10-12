import { describe, expect, it, vi } from 'vitest';
import { consumeSse, type SseFrame } from './sse';

function responseFromChunks(chunks: string[]) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    })
  );
}

describe('consumeSse', () => {
  it('preserves multiline data when CRLF is split between network chunks', async () => {
    const frames: SseFrame[] = [];
    await consumeSse(
      responseFromChunks([
        ': ping\r',
        '\nevent: delta\r',
        '\ndata: hello\r',
        '\ndata:  world\r',
        '\n\r',
        '\n',
      ]),
      frame => {
        frames.push(frame);
      }
    );
    expect(frames).toEqual([{ event: 'delta', data: 'hello\n world' }]);
  });

  it('does not dispatch a truncated final frame at EOF', async () => {
    const frames: SseFrame[] = [];
    await consumeSse(
      responseFromChunks(['event: final\ndata: {"content":"incomplete"}']),
      frame => {
        frames.push(frame);
      }
    );
    expect(frames).toEqual([]);
  });

  it('stops and cancels the reader without waiting for the server to close', async () => {
    const cancel = vi.fn();
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
        },
        cancel,
      })
    );
    await consumeSse(response, () => false);
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
  });
});
