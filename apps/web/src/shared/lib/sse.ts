export type SSEMessageType =
  | 'rag.status'
  | 'rag.embed.progress'
  | 'rag.tags.updated'
  | 'rag.deleted'
  | 'rag.snapshot'
  | 'rag.document_added'
  | 'rag.document_deleted';

export interface SSEMessage {
  type: SSEMessageType;
  data: any;
  timestamp: number;
  seq?: number;
}

export interface SSEClientOptions {
  url: string;
  onMessage: (events: SSEMessage[]) => void;
  batchInterval?: number;
  onError?: (event: Event) => void;
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
  private onErrorCallback: ((event: Event) => void) | null = null;
  // Manual reconnect is disabled; rely on native EventSource auto-reconnect
  private lastErrorLogAt = 0;
  private errorLogIntervalMs = 2000;
  private url: string;

  constructor(url: string, onBatch: (events: SSEMessage[]) => void);
  constructor(options: SSEClientOptions);
  constructor(
    urlOrOptions: string | SSEClientOptions,
    onBatch?: (events: SSEMessage[]) => void
  ) {
    if (typeof urlOrOptions === 'string') {
      this.url = urlOrOptions;
      this.onBatchCallback = onBatch ?? null;
      return;
    }

    this.url = urlOrOptions.url;
    this.onBatchCallback = urlOrOptions.onMessage;
    this.batchInterval = urlOrOptions.batchInterval ?? this.batchInterval;
    this.onErrorCallback = urlOrOptions.onError ?? null;
  }

  async connect(): Promise<void> {
    if (this.eventSource) {
      return;
    }

    const EventSourceCtorLocal = globalThis.EventSource;
    if (!EventSourceCtorLocal) {
      console.error('EventSource is not supported in this environment');
      return;
    }

    // Auth via httpOnly cookie — sent automatically with withCredentials: true
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

    // Connection opened
    this.eventSource.onopen = () => {
      // Connection established
    };

    // Default message handler (fallback for events without 'event:' field)
    this.eventSource.onmessage = event => {
      try {
        const parsed = JSON.parse(event.data);
        // Try to infer internal type
        const evt = (parsed?.event_type as string) || 'status_update';
        switch (evt) {
          case 'status_update':
          case 'status_initialized':
          case 'ingest_started':
          case 'aggregate_update':
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
        try {
          const parsed = JSON.parse(e.data.trim());
          push('rag.status', parsed);
        } catch (err) {
          console.error('[SSE] Failed to parse status_update:', err);
        }
      },
      status_initialized: e => {
        try {
          push('rag.status', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse status_initialized:', err);
        }
      },
      ingest_started: e => {
        try {
          push('rag.status', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse ingest_started:', err);
        }
      },
      aggregate_update: e => {
        try {
          push('rag.status', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse aggregate_update:', err);
        }
      },
      document_archived: e => {
        try {
          push('rag.deleted', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse document_archived:', err);
        }
      },
      document_unarchived: e => {
        try {
          push('rag.deleted', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse document_unarchived:', err);
        }
      },
      document_added: e => {
        try {
          push('rag.document_added', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse document_added:', err);
        }
      },
      document_deleted: e => {
        try {
          push('rag.document_deleted', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse document_deleted:', err);
        }
      },
      snapshot: e => {
        try {
          push('rag.snapshot', JSON.parse(e.data));
        } catch (err) {
          console.error('[SSE] Failed to parse snapshot:', err);
        }
      },
      heartbeat: _e => {
        // ignore
      },
      error: e => {
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
      this.onErrorCallback?.(error as Event);
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
  onBatch: (events: SSEMessage[]) => void,
): SSEClient => {
  const client = new SSEClient(url, onBatch);
  void client.connect();
  return client;
};
