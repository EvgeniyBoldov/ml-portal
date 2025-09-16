export type SSEEvent = { event?: string; data?: string; id?: string };
export async function* parseSSE(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 2);
        if (!chunk) continue;
        const ev: SSEEvent = {};
        for (const line of chunk.split('\n')) {
          const [k, ...rest] = line.split(':');
          const v = rest.join(':').trimStart();
          if (k === 'event') ev.event = v;
          else if (k === 'data') ev.data = (ev.data ? ev.data + '\n' : '') + v;
          else if (k === 'id') ev.id = v;
        }
        yield ev;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
