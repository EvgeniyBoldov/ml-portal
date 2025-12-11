import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SSEClient, SSEMessage } from '@shared/lib/sse';

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  
  url: string;
  withCredentials: boolean;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState: number = 0;
  
  constructor(url: string, options?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = options?.withCredentials ?? false;
    MockEventSource.instances.push(this);
  }
  
  close() {
    this.readyState = 2;
  }
  
  // Helper to simulate events
  simulateOpen() {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }
  
  simulateMessage(data: string, type = 'message') {
    this.onmessage?.(new MessageEvent(type, { data }));
  }
  
  simulateError() {
    this.onerror?.(new Event('error'));
  }
  
  static reset() {
    MockEventSource.instances = [];
  }
}

// Replace global EventSource
const originalEventSource = globalThis.EventSource;

describe('SSEClient', () => {
  beforeEach(() => {
    MockEventSource.reset();
    (globalThis as any).EventSource = MockEventSource;
  });
  
  afterEach(() => {
    (globalThis as any).EventSource = originalEventSource;
  });
  
  describe('connection', () => {
    it('should create EventSource with correct URL', () => {
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage: vi.fn(),
      });
      
      client.connect();
      
      expect(MockEventSource.instances).toHaveLength(1);
      expect(MockEventSource.instances[0].url).toBe('http://localhost:8000/api/v1/rag/events');
    });
    
    it('should set withCredentials to true', () => {
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage: vi.fn(),
      });
      
      client.connect();
      
      expect(MockEventSource.instances[0].withCredentials).toBe(true);
    });
    
    it('should append token to URL if getAccessToken provided', async () => {
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage: vi.fn(),
        getAccessToken: async () => 'test-token-123',
      });
      
      await client.connect();
      
      expect(MockEventSource.instances[0].url).toContain('token=test-token-123');
    });
  });
  
  describe('message handling', () => {
    it('should parse and deliver messages to callback', () => {
      const onMessage = vi.fn();
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage,
      });
      
      client.connect();
      
      const eventSource = MockEventSource.instances[0];
      eventSource.simulateOpen();
      eventSource.simulateMessage(JSON.stringify({
        type: 'rag.status',
        doc_id: 'doc-123',
        stage: 'extract',
        status: 'processing',
      }));
      
      expect(onMessage).toHaveBeenCalled();
      const messages = onMessage.mock.calls[0][0] as SSEMessage[];
      expect(messages).toHaveLength(1);
      expect(messages[0].type).toBe('rag.status');
      expect(messages[0].data.doc_id).toBe('doc-123');
    });
    
    it('should handle malformed JSON gracefully', () => {
      const onMessage = vi.fn();
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage,
      });
      
      client.connect();
      
      const eventSource = MockEventSource.instances[0];
      eventSource.simulateOpen();
      eventSource.simulateMessage('not valid json');
      
      // Should not crash, should log error
      expect(consoleSpy).toHaveBeenCalled();
      
      consoleSpy.mockRestore();
    });
    
    it('should ignore heartbeat messages', () => {
      const onMessage = vi.fn();
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage,
      });
      
      client.connect();
      
      const eventSource = MockEventSource.instances[0];
      eventSource.simulateOpen();
      eventSource.simulateMessage(JSON.stringify({ type: 'heartbeat' }));
      
      // Heartbeat should not trigger onMessage
      expect(onMessage).not.toHaveBeenCalled();
    });
  });
  
  describe('batching', () => {
    it('should batch multiple messages within interval', async () => {
      vi.useFakeTimers();
      
      const onMessage = vi.fn();
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage,
        batchInterval: 100,
      });
      
      client.connect();
      
      const eventSource = MockEventSource.instances[0];
      eventSource.simulateOpen();
      
      // Send multiple messages quickly
      eventSource.simulateMessage(JSON.stringify({ type: 'rag.status', doc_id: '1' }));
      eventSource.simulateMessage(JSON.stringify({ type: 'rag.status', doc_id: '2' }));
      eventSource.simulateMessage(JSON.stringify({ type: 'rag.status', doc_id: '3' }));
      
      // Should not have called yet (batching)
      expect(onMessage).not.toHaveBeenCalled();
      
      // Advance timer past batch interval
      vi.advanceTimersByTime(150);
      
      // Now should have called with all messages
      expect(onMessage).toHaveBeenCalledTimes(1);
      const messages = onMessage.mock.calls[0][0] as SSEMessage[];
      expect(messages).toHaveLength(3);
      
      vi.useRealTimers();
    });
  });
  
  describe('disconnect', () => {
    it('should close EventSource on disconnect', () => {
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage: vi.fn(),
      });
      
      client.connect();
      
      const eventSource = MockEventSource.instances[0];
      expect(eventSource.readyState).not.toBe(2);
      
      client.disconnect();
      
      expect(eventSource.readyState).toBe(2);
    });
  });
  
  describe('reconnection', () => {
    it('should call onError callback on connection error', () => {
      const onError = vi.fn();
      const client = new SSEClient({
        url: 'http://localhost:8000/api/v1/rag/events',
        onMessage: vi.fn(),
        onError,
      });
      
      client.connect();
      
      const eventSource = MockEventSource.instances[0];
      eventSource.simulateError();
      
      expect(onError).toHaveBeenCalled();
    });
  });
});
