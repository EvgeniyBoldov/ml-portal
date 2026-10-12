import { createParser } from 'eventsource-parser';

export type SseFrame = {
  event: string;
  data: string;
};

/** Consume a fetch-based SSE response, preserving named events and multiline data. */
export async function consumeSse(
  response: Response,
  onFrame: (frame: SseFrame) => void | boolean | Promise<void | boolean>
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('SSE response has no body');

  const decoder = new TextDecoder();
  const frames: SseFrame[] = [];
  const parser = createParser({
    onEvent: ({ event, data }) => {
      frames.push({ event: event || 'message', data });
    },
  });
  let hasReachedEof = false;
  try {
    while (!hasReachedEof) {
      const { done, value } = await reader.read();
      hasReachedEof = done;
      parser.feed(decoder.decode(value, { stream: !done }));
      for (const frame of frames.splice(0)) {
        if ((await onFrame(frame)) === false) return;
      }
    }
    // A missing blank line is an incomplete event, not an authoritative FINAL.
  } finally {
    if (!hasReachedEof) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
