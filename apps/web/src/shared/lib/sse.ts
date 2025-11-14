export type SSEMessageType =
  | 'rag.status'
  | 'rag.embed.progress'
  | 'rag.tags.updated'
  | 'rag.deleted';

export interface SSEMessage {
  type: SSEMessageType;
  data: any;
  timestamp: number;
  seq?: number;
}

export interface RAGStatusEvent {
  id: string;
  status: string;
  error_message?: string;
  updated_at?: string;
}

export interface RAGEmbedProgressEvent {
  id: string;
  model_alias: string;
  done_count: number;
  total_count: number;
  last_error?: string;
  updated_at?: string;
}

export interface RAGTagsUpdatedEvent {
  id: string;
  tags: string[];
  updated_at?: string;
}

export interface RAGDeletedEvent {
  id: string;
}

type EventBuffer = SSEMessage[];

type EventSourceCtor = typeof globalThis extends { EventSource: infer ES }
  ? ES
  : undefined;

type EventSourceInstance = EventSourceCtor extends {
  prototype: infer P;
}
  ? P
  : undefined;

export class SSEClient {
  private eventSource: EventSourceInstance | null = null;
  private buffer: EventBuffer = [];
  private batchInterval: number = 100; // ms
  private intervalId: ReturnType<typeof globalThis.setInterval> | null = null;
  private onBatchCallback: ((events: SSEMessage[]) => void) | null = null;
  // Manual reconnect is disabled; rely on native EventSource auto-reconnect
  private lastErrorLogAt = 0;
  private errorLogIntervalMs = 2000;

  constructor(
    private url: string,
    private onBatch: (events: SSEMessage[]) => void
  ) {
    this.onBatchCallback = onBatch;
  }

  connect(): void {
    if (this.eventSource) {
      return;
    }

    const EventSourceCtorLocal = globalThis.EventSource;
    if (!EventSourceCtorLocal) {
      console.error('EventSource is not supported in this environment');
      return;
    }

    // EventSource with withCredentials: true automatically sends httpOnly cookies
    // No need for token in query params or custom headers
    this.eventSource = new EventSourceCtorLocal(this.url, {
      withCredentials: true,
    }) as EventSourceInstance;

    const push = (type: SSEMessageType, raw: any) => {
      const msg: SSEMessage = {
        type,
        data: raw,
        timestamp: raw?.timestamp || Date.now(),
        seq: raw?.seq,
      };
      this.buffer.push(msg);
    };

    // Default message handler (fallback)
    this.eventSource.onmessage = event => {
      try {
        const parsed = JSON.parse(event.data);
        // Try to infer internal type
        const evt = (parsed?.event_type as string) || 'status_update';
        switch (evt) {
          case 'status_update':
          case 'status_initialized':
          case 'ingest_started':
            push('rag.status', parsed);
            break;
          case 'document_archived':
          case 'document_unarchived':
            push('rag.deleted', parsed);
            break;
          default:
            // Unknown → still push as status to not lose updates
            push('rag.status', parsed);
        }
      } catch (error) {
        console.error('Failed to parse SSE message:', error);
      }
    };

    // Named events from backend
    const namedHandlers: Record<string, (e: MessageEvent) => void> = {
      status_update: e => {
        try { push('rag.status', JSON.parse(e.data)); } catch {}
      },
      status_initialized: e => {
        try { push('rag.status', JSON.parse(e.data)); } catch {}
      },
      ingest_started: e => {
        try { push('rag.status', JSON.parse(e.data)); } catch {}
      },
      document_archived: e => {
        try { push('rag.deleted', JSON.parse(e.data)); } catch {}
      },
      document_unarchived: e => {
        try { push('rag.deleted', JSON.parse(e.data)); } catch {}
      },
      heartbeat: e => {
        // ignore
      },
      error: e => {
        // backend may emit error events as SSE too
        try { console.warn('SSE server error event:', JSON.parse(e.data)); } catch {}
      },
    };

    Object.entries(namedHandlers).forEach(([name, handler]) => {
      this.eventSource!.addEventListener(name, handler as EventListener);
    });

    this.eventSource.onerror = (error: any) => {
      const now = Date.now();
      if (now - this.lastErrorLogAt > this.errorLogIntervalMs) {
        console.error('SSE connection error:', error);
        this.lastErrorLogAt = now;
      }
      // Do not manually reconnect; EventSource will auto-retry
    };

    // Start batching
    this.startBatching();
  }

  private startBatching(): void {
    this.intervalId = globalThis.setInterval(() => {
      if (this.buffer.length > 0 && this.onBatchCallback) {
        const events = [...this.buffer];
        this.buffer = [];
        this.onBatchCallback(events);
      }
    }, this.batchInterval);
  }

  // Manual reconnect logic removed to avoid reconnection storms

  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    if (this.intervalId) {
      globalThis.clearInterval(this.intervalId);
      this.intervalId = null;
    }

    this.buffer = [];
  }

  isConnected(): boolean {
    const EventSourceCtorLocal = globalThis.EventSource;
    if (!this.eventSource || !EventSourceCtorLocal) {
      return false;
    }

    return this.eventSource.readyState === EventSourceCtorLocal.OPEN;
  }
}

export const openSSE = (
  url: string,
  onBatch: (events: SSEMessage[]) => void
): SSEClient => {
  const client = new SSEClient(url, onBatch);
  client.connect();
  return client;
};
