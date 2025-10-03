import { test, expect } from '@playwright/test';

test.describe('Server-Sent Events (SSE) E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Chat Response Streaming', async ({ page }) => {
    // Create a chat first
    const chatResponse = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `sse-chat-${Date.now()}`
      },
      data: {
        name: 'SSE Test Chat'
      }
    });
    
    const chat = await chatResponse.json();
    
    // Send a message that should trigger streaming response
    const messageResponse = await page.request.post(`/api/v1/chats/${chat.id}/messages`, {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `sse-msg-${Date.now()}`
      },
      data: {
        content: 'Hello, please respond with a long message',
        role: 'user'
      }
    });
    
    expect(messageResponse.status()).toBe(201);
    
    // Listen for SSE events
    const events = [];
    await page.exposeFunction('onSSEEvent', (event) => {
      events.push(event);
    });
    
    // Start SSE connection
    await page.evaluate(async (chatId) => {
      const eventSource = new EventSource(`/api/v1/chats/${chatId}/stream`);
      
      eventSource.onmessage = (event) => {
        window.onSSEEvent({
          type: 'message',
          data: event.data
        });
      };
      
      eventSource.addEventListener('done', (event) => {
        window.onSSEEvent({
          type: 'done',
          data: event.data
        });
        eventSource.close();
      });
      
      eventSource.addEventListener('error', (event) => {
        window.onSSEEvent({
          type: 'error',
          data: event.data
        });
        eventSource.close();
      });
      
      // Store reference for cleanup
      window.sseConnection = eventSource;
    }, chat.id);
    
    // Wait for events
    await page.waitForFunction(() => window.events && window.events.length > 0, { timeout: 10000 });
    
    // Verify we received streaming events
    expect(events.length).toBeGreaterThan(0);
    
    // Check for done event
    const doneEvent = events.find(e => e.type === 'done');
    expect(doneEvent).toBeTruthy();
    
    // Cleanup
    await page.evaluate(() => {
      if (window.sseConnection) {
        window.sseConnection.close();
      }
    });
  });

  test('Document Processing Streaming', async ({ page }) => {
    // Upload a document first
    const docResponse = await page.request.post('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `sse-doc-${Date.now()}`
      },
      data: {
        filename: 'test-document.txt',
        title: 'SSE Test Document',
        content_type: 'text/plain',
        size: 2048
      }
    });
    
    const document = await docResponse.json();
    
    // Start document processing
    const processResponse = await page.request.post(`/api/v1/rag/documents/${document.id}/process`, {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `process-${Date.now()}`
      }
    });
    
    expect(processResponse.status()).toBe(202); // Accepted for processing
    
    // Listen for processing events
    const events = [];
    await page.exposeFunction('onProcessEvent', (event) => {
      events.push(event);
    });
    
    // Start SSE connection for processing
    await page.evaluate(async (docId) => {
      const eventSource = new EventSource(`/api/v1/rag/documents/${docId}/process/stream`);
      
      eventSource.onmessage = (event) => {
        window.onProcessEvent({
          type: 'progress',
          data: event.data
        });
      };
      
      eventSource.addEventListener('completed', (event) => {
        window.onProcessEvent({
          type: 'completed',
          data: event.data
        });
        eventSource.close();
      });
      
      eventSource.addEventListener('error', (event) => {
        window.onProcessEvent({
          type: 'error',
          data: event.data
        });
        eventSource.close();
      });
      
      window.processConnection = eventSource;
    }, document.id);
    
    // Wait for completion
    await page.waitForFunction(() => {
      return window.processEvents && window.processEvents.some(e => e.type === 'completed' || e.type === 'error');
    }, { timeout: 15000 });
    
    // Verify we received processing events
    expect(events.length).toBeGreaterThan(0);
    
    // Cleanup
    await page.evaluate(() => {
      if (window.processConnection) {
        window.processConnection.close();
      }
    });
  });

  test('SSE Heartbeat for Long Operations', async ({ page }) => {
    // Start a long-running operation
    const longResponse = await page.request.post('/api/v1/analyze/long-task', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `long-task-${Date.now()}`
      },
      data: {
        duration: 30 // 30 seconds
      }
    });
    
    expect(longResponse.status()).toBe(202);
    
    // Listen for heartbeat events
    const heartbeats = [];
    await page.exposeFunction('onHeartbeat', (event) => {
      heartbeats.push(event);
    });
    
    // Start SSE connection
    await page.evaluate(async () => {
      const eventSource = new EventSource('/api/v1/analyze/long-task/stream');
      
      eventSource.addEventListener('heartbeat', (event) => {
        window.onHeartbeat({
          type: 'heartbeat',
          timestamp: new Date().toISOString(),
          data: event.data
        });
      });
      
      eventSource.addEventListener('completed', (event) => {
        window.onHeartbeat({
          type: 'completed',
          data: event.data
        });
        eventSource.close();
      });
      
      window.heartbeatConnection = eventSource;
    });
    
    // Wait for at least 2 heartbeats (should happen every 10 seconds)
    await page.waitForFunction(() => {
      return window.heartbeats && window.heartbeats.length >= 2;
    }, { timeout: 25000 });
    
    // Verify we received heartbeats
    expect(heartbeats.length).toBeGreaterThanOrEqual(2);
    
    // Verify heartbeat timing (should be roughly every 10 seconds)
    const timestamps = heartbeats.map(h => new Date(h.timestamp).getTime());
    for (let i = 1; i < timestamps.length; i++) {
      const interval = timestamps[i] - timestamps[i - 1];
      expect(interval).toBeGreaterThan(8000); // At least 8 seconds
      expect(interval).toBeLessThan(12000); // At most 12 seconds
    }
    
    // Cleanup
    await page.evaluate(() => {
      if (window.heartbeatConnection) {
        window.heartbeatConnection.close();
      }
    });
  });

  test('SSE Connection Cleanup on Page Unload', async ({ page }) => {
    // Create a chat
    const chatResponse = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `cleanup-chat-${Date.now()}`
      },
      data: {
        name: 'Cleanup Test Chat'
      }
    });
    
    const chat = await chatResponse.json();
    
    // Start SSE connection
    await page.evaluate(async (chatId) => {
      const eventSource = new EventSource(`/api/v1/chats/${chatId}/stream`);
      
      eventSource.onopen = () => {
        console.log('SSE connection opened');
      };
      
      eventSource.onclose = () => {
        console.log('SSE connection closed');
      };
      
      window.sseConnection = eventSource;
    }, chat.id);
    
    // Verify connection is open
    await page.waitForFunction(() => window.sseConnection && window.sseConnection.readyState === 1);
    
    // Navigate away (simulate page unload)
    await page.goto('/dashboard');
    
    // Wait a bit for cleanup
    await page.waitForTimeout(1000);
    
    // Verify connection was closed
    const connectionState = await page.evaluate(() => {
      return window.sseConnection ? window.sseConnection.readyState : 'closed';
    });
    
    expect(connectionState).toBe(3); // CLOSED state
  });

  test('SSE Error Handling', async ({ page }) => {
    // Try to connect to non-existent stream
    const events = [];
    await page.exposeFunction('onSSEError', (event) => {
      events.push(event);
    });
    
    await page.evaluate(async () => {
      const eventSource = new EventSource('/api/v1/chats/non-existent/stream');
      
      eventSource.addEventListener('error', (event) => {
        window.onSSEError({
          type: 'error',
          readyState: eventSource.readyState
        });
        eventSource.close();
      });
      
      window.errorConnection = eventSource;
    });
    
    // Wait for error event
    await page.waitForFunction(() => {
      return window.errorEvents && window.errorEvents.length > 0;
    }, { timeout: 5000 });
    
    // Verify we received an error
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].type).toBe('error');
    
    // Cleanup
    await page.evaluate(() => {
      if (window.errorConnection) {
        window.errorConnection.close();
      }
    });
  });

  test('Multiple SSE Connections', async ({ page }) => {
    // Create multiple chats
    const chats = [];
    for (let i = 0; i < 3; i++) {
      const chatResponse = await page.request.post('/api/v1/chats', {
        headers: {
          'X-Tenant-Id': 'test-tenant-id',
          'Idempotency-Key': `multi-chat-${i}-${Date.now()}`
        },
        data: {
          name: `Multi Chat ${i + 1}`
        }
      });
      chats.push(await chatResponse.json());
    }
    
    // Start multiple SSE connections
    const connections = [];
    await page.evaluate(async (chatIds) => {
      const connections = [];
      
      for (const chatId of chatIds) {
        const eventSource = new EventSource(`/api/v1/chats/${chatId}/stream`);
        connections.push(eventSource);
      }
      
      window.multipleConnections = connections;
    }, chats.map(c => c.id));
    
    // Verify all connections are open
    const connectionStates = await page.evaluate(() => {
      return window.multipleConnections.map(conn => conn.readyState);
    });
    
    expect(connectionStates.every(state => state === 1)).toBe(true); // All OPEN
    
    // Close all connections
    await page.evaluate(() => {
      window.multipleConnections.forEach(conn => conn.close());
    });
    
    // Verify all connections are closed
    const closedStates = await page.evaluate(() => {
      return window.multipleConnections.map(conn => conn.readyState);
    });
    
    expect(closedStates.every(state => state === 3)).toBe(true); // All CLOSED
  });
});
