import { test, expect } from '@playwright/test';

test.describe('Cursor Pagination E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Chat List Pagination', async ({ page }) => {
    // Create multiple chats for pagination testing
    const chatNames = [];
    for (let i = 0; i < 25; i++) {
      chatNames.push(`Pagination Test Chat ${i + 1}`);
    }
    
    // Create chats
    for (const chatName of chatNames) {
      await page.request.post('/api/v1/chats', {
        headers: {
          'X-Tenant-Id': 'test-tenant-id',
          'Idempotency-Key': `chat-${chatName}-${Date.now()}`
        },
        data: {
          name: chatName
        }
      });
    }
    
    // Test first page
    const page1Response = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 10
      }
    });
    
    expect(page1Response.status()).toBe(200);
    const page1Data = await page1Response.json();
    
    expect(page1Data).toHaveProperty('items');
    expect(page1Data).toHaveProperty('next_cursor');
    expect(page1Data).toHaveProperty('has_next');
    expect(page1Data.items).toHaveLength(10);
    expect(page1Data.has_next).toBe(true);
    
    // Test second page using cursor
    const page2Response = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 10,
        cursor: page1Data.next_cursor
      }
    });
    
    expect(page2Response.status()).toBe(200);
    const page2Data = await page2Response.json();
    
    expect(page2Data.items).toHaveLength(10);
    expect(page2Data.has_next).toBe(true);
    
    // Verify no overlap between pages
    const page1Ids = page1Data.items.map(item => item.id);
    const page2Ids = page2Data.items.map(item => item.id);
    const overlap = page1Ids.filter(id => page2Ids.includes(id));
    expect(overlap).toHaveLength(0);
  });

  test('Chat Messages Pagination', async ({ page }) => {
    // Create a chat first
    const chatResponse = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `messages-chat-${Date.now()}`
      },
      data: {
        name: 'Messages Pagination Test'
      }
    });
    
    const chat = await chatResponse.json();
    
    // Create multiple messages
    const messages = [];
    for (let i = 0; i < 15; i++) {
      messages.push(`Test message ${i + 1}`);
    }
    
    for (const message of messages) {
      await page.request.post(`/api/v1/chats/${chat.id}/messages`, {
        headers: {
          'X-Tenant-Id': 'test-tenant-id',
          'Idempotency-Key': `msg-${message}-${Date.now()}`
        },
        data: {
          content: message,
          role: 'user'
        }
      });
    }
    
    // Test first page of messages
    const page1Response = await page.request.get(`/api/v1/chats/${chat.id}/messages`, {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 5
      }
    });
    
    expect(page1Response.status()).toBe(200);
    const page1Data = await page1Response.json();
    
    expect(page1Data.items).toHaveLength(5);
    expect(page1Data.has_next).toBe(true);
    
    // Test second page
    const page2Response = await page.request.get(`/api/v1/chats/${chat.id}/messages`, {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 5,
        cursor: page1Data.next_cursor
      }
    });
    
    expect(page2Response.status()).toBe(200);
    const page2Data = await page2Response.json();
    
    expect(page2Data.items).toHaveLength(5);
    
    // Verify chronological order (newest first)
    const page1Timestamps = page1Data.items.map(item => new Date(item.created_at).getTime());
    const page2Timestamps = page2Data.items.map(item => new Date(item.created_at).getTime());
    
    // Page 1 should have newer messages than page 2
    const maxPage1 = Math.max(...page1Timestamps);
    const minPage2 = Math.min(...page2Timestamps);
    expect(maxPage1).toBeGreaterThan(minPage2);
  });

  test('Document List Pagination', async ({ page }) => {
    // Create multiple documents
    const documents = [];
    for (let i = 0; i < 20; i++) {
      documents.push({
        filename: `document-${i + 1}.txt`,
        title: `Document ${i + 1}`,
        content_type: 'text/plain',
        size: 1024 + i
      });
    }
    
    for (const doc of documents) {
      await page.request.post('/api/v1/rag/documents', {
        headers: {
          'X-Tenant-Id': 'test-tenant-id',
          'Idempotency-Key': `doc-${doc.filename}-${Date.now()}`
        },
        data: doc
      });
    }
    
    // Test pagination
    const page1Response = await page.request.get('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 8
      }
    });
    
    expect(page1Response.status()).toBe(200);
    const page1Data = await page1Response.json();
    
    expect(page1Data.items).toHaveLength(8);
    expect(page1Data.has_next).toBe(true);
    
    // Test next page
    const page2Response = await page.request.get('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 8,
        cursor: page1Data.next_cursor
      }
    });
    
    expect(page2Response.status()).toBe(200);
    const page2Data = await page2Response.json();
    
    expect(page2Data.items).toHaveLength(8);
  });

  test('Invalid Cursor Handling', async ({ page }) => {
    // Test with invalid cursor format
    const response = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 10,
        cursor: 'invalid-cursor-format'
      }
    });
    
    // Should return 400 Bad Request
    expect(response.status()).toBe(400);
  });

  test('Cursor Stability', async ({ page }) => {
    // Get first page
    const page1Response = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 5
      }
    });
    
    const page1Data = await page1Response.json();
    const cursor = page1Data.next_cursor;
    
    // Make same request multiple times with same cursor
    const responses = [];
    for (let i = 0; i < 3; i++) {
      const response = await page.request.get('/api/v1/chats', {
        headers: {
          'X-Tenant-Id': 'test-tenant-id'
        },
        params: {
          limit: 5,
          cursor: cursor
        }
      });
      
      responses.push(await response.json());
    }
    
    // All responses should be identical
    for (let i = 1; i < responses.length; i++) {
      expect(responses[i].items).toEqual(responses[0].items);
      expect(responses[i].next_cursor).toBe(responses[0].next_cursor);
    }
  });

  test('Limit Boundaries', async ({ page }) => {
    // Test minimum limit
    const minResponse = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 1
      }
    });
    
    expect(minResponse.status()).toBe(200);
    const minData = await minResponse.json();
    expect(minData.items).toHaveLength(1);
    
    // Test maximum limit
    const maxResponse = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 100
      }
    });
    
    expect(maxResponse.status()).toBe(200);
    const maxData = await maxResponse.json();
    expect(maxData.items.length).toBeLessThanOrEqual(100);
    
    // Test limit exceeding maximum
    const exceedResponse = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 1000
      }
    });
    
    // Should return 400 Bad Request
    expect(exceedResponse.status()).toBe(400);
  });
});
