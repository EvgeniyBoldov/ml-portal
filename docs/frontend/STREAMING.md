# Стримы и SSE (Frontend)

## Обзор

Клиентская часть SSE для real-time обновлений.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      SSE Architecture                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SSEProvider (global)                                       │
│       │                                                     │
│       ├─► SSEClient (EventSource wrapper)                   │
│       │       │                                             │
│       │       └─► Events → applyRagEvents()                 │
│       │                         │                           │
│       │                         └─► QueryClient.setQueryData│
│       │                                                     │
│       └─► Subscriptions management                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## SSE Client

```typescript
// shared/lib/sse.ts
interface SSEClientOptions {
  getAccessToken: () => string | null;
  onMessage?: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  reconnectDelay?: number;
  maxRetries?: number;
}

class SSEClient {
  private eventSource: EventSource | null = null;
  private retryCount = 0;
  
  constructor(
    private url: string,
    private options: SSEClientOptions
  ) {}
  
  connect(): void {
    const token = this.options.getAccessToken();
    const urlWithToken = `${this.url}?token=${token}`;
    
    this.eventSource = new EventSource(urlWithToken, {
      withCredentials: true,
    });
    
    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.options.onMessage?.(data);
    };
    
    this.eventSource.onerror = () => {
      this.handleError();
    };
  }
  
  disconnect(): void {
    this.eventSource?.close();
    this.eventSource = null;
  }
  
  private handleError(): void {
    this.disconnect();
    
    if (this.retryCount < (this.options.maxRetries ?? 5)) {
      this.retryCount++;
      const delay = this.options.reconnectDelay ?? 3000;
      setTimeout(() => this.connect(), delay * this.retryCount);
    }
  }
}
```

## SSE Provider

```tsx
// app/providers/SSEProvider.tsx
import { createContext, useContext, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { SSEClient } from '@shared/lib/sse';
import { applyRagEvents } from './applyRagEvents';
import { config } from '@shared/config';
import { getAccessToken } from '@shared/api/http';

interface SSEContextValue {
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
}

const SSEContext = createContext<SSEContextValue | null>(null);

export function SSEProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const clientRef = useRef<SSEClient | null>(null);
  
  useEffect(() => {
    const client = new SSEClient(config.sseUrl, {
      getAccessToken,
      onMessage: (event) => {
        applyRagEvents(queryClient, event);
      },
      onError: (error) => {
        console.error('SSE error:', error);
      },
    });
    
    client.connect();
    clientRef.current = client;
    
    return () => {
      client.disconnect();
    };
  }, [queryClient]);
  
  const value: SSEContextValue = {
    subscribe: (channel) => {
      // POST /api/v1/sse/subscribe
    },
    unsubscribe: (channel) => {
      // POST /api/v1/sse/unsubscribe
    },
  };
  
  return (
    <SSEContext.Provider value={value}>
      {children}
    </SSEContext.Provider>
  );
}

export function useSSE() {
  const context = useContext(SSEContext);
  if (!context) {
    throw new Error('useSSE must be used within SSEProvider');
  }
  return context;
}
```

## Event Handlers

### RAG Events

```typescript
// app/providers/applyRagEvents.ts
import { QueryClient } from '@tanstack/react-query';
import { qk } from '@shared/api/keys';

interface RagEvent {
  type: string;
  document_id?: string;
  status?: string;
  stage?: string;
  progress?: number;
  timestamp: string;
}

export function applyRagEvents(
  queryClient: QueryClient,
  event: RagEvent
): void {
  switch (event.type) {
    case 'document.created':
      queryClient.invalidateQueries({ queryKey: qk.rag.list() });
      break;
      
    case 'document.status_changed':
      if (event.document_id) {
        // Update detail cache
        queryClient.setQueryData(
          qk.rag.detail(event.document_id),
          (old: any) => old ? { ...old, status: event.status } : old
        );
        // Invalidate list for status badge update
        queryClient.invalidateQueries({ queryKey: qk.rag.list() });
      }
      break;
      
    case 'stage.progress':
      if (event.document_id) {
        queryClient.setQueryData(
          qk.rag.detail(event.document_id),
          (old: any) => {
            if (!old) return old;
            return {
              ...old,
              pipeline: {
                ...old.pipeline,
                [event.stage!]: {
                  ...old.pipeline?.[event.stage!],
                  progress: event.progress,
                },
              },
            };
          }
        );
      }
      break;
      
    case 'document.deleted':
      if (event.document_id) {
        queryClient.removeQueries({ 
          queryKey: qk.rag.detail(event.document_id) 
        });
        queryClient.invalidateQueries({ queryKey: qk.rag.list() });
      }
      break;
  }
}
```

### Chat Events

```typescript
// domains/chat/hooks/useChatStream.ts
interface ChatEvent {
  type: 'delta' | 'tool_call' | 'tool_result' | 'done' | 'error';
  content?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: string;
  message?: string;
}

export function useChatStream(chatId: string, streamId: string) {
  const [content, setContent] = useState('');
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [isStreaming, setIsStreaming] = useState(true);
  
  useEffect(() => {
    const sse = new SSEClient(`/api/v1/chats/${chatId}/stream/${streamId}`, {
      getAccessToken,
      onMessage: (event: ChatEvent) => {
        switch (event.type) {
          case 'delta':
            setContent((prev) => prev + (event.content || ''));
            break;
            
          case 'tool_call':
            setToolCalls((prev) => [...prev, {
              tool: event.tool!,
              arguments: event.arguments!,
              status: 'running',
            }]);
            break;
            
          case 'tool_result':
            setToolCalls((prev) => prev.map((tc) =>
              tc.tool === event.tool
                ? { ...tc, result: event.result, status: 'completed' }
                : tc
            ));
            break;
            
          case 'done':
            setIsStreaming(false);
            break;
            
          case 'error':
            setIsStreaming(false);
            // Handle error
            break;
        }
      },
    });
    
    sse.connect();
    
    return () => sse.disconnect();
  }, [chatId, streamId]);
  
  return { content, toolCalls, isStreaming };
}
```

## Типы событий

### RAG

| Event | Описание | Payload |
|-------|----------|---------|
| `document.created` | Новый документ | `{ document_id }` |
| `document.status_changed` | Изменение статуса | `{ document_id, status }` |
| `stage.started` | Начало стадии | `{ document_id, stage }` |
| `stage.progress` | Прогресс стадии | `{ document_id, stage, progress }` |
| `stage.completed` | Завершение стадии | `{ document_id, stage }` |
| `stage.failed` | Ошибка стадии | `{ document_id, stage, error }` |
| `document.deleted` | Удаление документа | `{ document_id }` |

### Chat

| Event | Описание | Payload |
|-------|----------|---------|
| `delta` | Часть текста | `{ content }` |
| `tool_call` | Вызов инструмента | `{ tool, arguments }` |
| `tool_result` | Результат инструмента | `{ tool, result }` |
| `status` | Статусное сообщение | `{ message }` |
| `done` | Завершение | `{}` |
| `error` | Ошибка | `{ message }` |

## Reconnection Strategy

```typescript
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]; // Exponential backoff

class SSEClient {
  private retryCount = 0;
  
  private handleError(): void {
    this.disconnect();
    
    if (this.retryCount < RECONNECT_DELAYS.length) {
      const delay = RECONNECT_DELAYS[this.retryCount];
      this.retryCount++;
      
      console.log(`SSE reconnecting in ${delay}ms (attempt ${this.retryCount})`);
      
      setTimeout(() => this.connect(), delay);
    } else {
      console.error('SSE max retries reached');
      this.options.onError?.(new Error('Max retries reached'));
    }
  }
  
  private resetRetryCount(): void {
    this.retryCount = 0;
  }
}
```

## UI Indicators

### Connection Status

```tsx
function ConnectionStatus() {
  const { isConnected, isReconnecting } = useSSE();
  
  if (isReconnecting) {
    return (
      <div className={styles.reconnecting}>
        <Spinner size="small" />
        Переподключение...
      </div>
    );
  }
  
  if (!isConnected) {
    return (
      <div className={styles.disconnected}>
        <Icon name="wifi-off" />
        Нет соединения
      </div>
    );
  }
  
  return null;
}
```

### Progress Indicator

```tsx
function DocumentProgress({ documentId }: { documentId: string }) {
  const { data } = useQuery({
    queryKey: qk.rag.detail(documentId),
    queryFn: () => ragApi.get(documentId),
  });
  
  if (!data?.pipeline) return null;
  
  const stages = ['extract', 'chunk', 'embed'];
  
  return (
    <div className={styles.progress}>
      {stages.map((stage) => (
        <StageProgress
          key={stage}
          stage={stage}
          status={data.pipeline[stage]?.status}
          progress={data.pipeline[stage]?.progress}
        />
      ))}
    </div>
  );
}
```
