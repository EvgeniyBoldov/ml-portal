export type SseFrame = {
  event: string;
  data: string;
};

function parseFrame(rawFrame: string): SseFrame | null {
  let event = 'message';
  const data: string[] = [];

  for (const line of rawFrame.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? '' : line.slice(separator + 1).replace(/^ /, '');
    if (field === 'event') event = value;
    if (field === 'data') data.push(value);
  }

  return data.length > 0 ? { event, data: data.join('\n') } : null;
}

/** Consume a fetch-based SSE response, preserving named events and multiline data. */
export async function consumeSse(
  response: Response,
  onFrame: (frame: SseFrame) => void | Promise<void>,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('SSE response has no body');

  const decoder = new TextDecoder();
  let buffer = '';
  const dispatch = async (rawFrame: string) => {
    const frame = parseFrame(rawFrame);
    if (frame) await onFrame(frame);
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const rawFrame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      await dispatch(rawFrame);
      boundary = buffer.indexOf('\n\n');
    }
    if (done) break;
  }

  if (buffer.trim()) await dispatch(buffer);
}
