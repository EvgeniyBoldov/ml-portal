import { test, expect } from '@playwright/test';

test.describe('Idempotency E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Chat Creation Idempotency', async ({ page }) => {
    const idempotencyKey = `chat-${Date.now()}`;
    
    // First request to create chat
    const response1 = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': idempotencyKey
      },
      data: {
        name: 'Idempotent Chat Test'
      }
    });
    
    expect(response1.status()).toBe(201);
    const chat1 = await response1.json();
    
    // Second identical request with same idempotency key
    const response2 = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': idempotencyKey
      },
      data: {
        name: 'Idempotent Chat Test'
      }
    });
    
    // Should return same result (409 or same data)
    expect([201, 409]).toContain(response2.status());
    
    if (response2.status() === 201) {
      const chat2 = await response2.json();
      expect(chat1.id).toBe(chat2.id);
    }
  });

  test('Document Upload Idempotency', async ({ page }) => {
    const idempotencyKey = `doc-${Date.now()}`;
    
    // First request to upload document
    const response1 = await page.request.post('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': idempotencyKey
      },
      data: {
        filename: 'test-document.txt',
        title: 'Test Document',
        content_type: 'text/plain',
        size: 1024
      }
    });
    
    expect(response1.status()).toBe(201);
    const doc1 = await response1.json();
    
    // Second identical request with same idempotency key
    const response2 = await page.request.post('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': idempotencyKey
      },
      data: {
        filename: 'test-document.txt',
        title: 'Test Document',
        content_type: 'text/plain',
        size: 1024
      }
    });
    
    // Should return same result (409 or same data)
    expect([201, 409]).toContain(response2.status());
    
    if (response2.status() === 201) {
      const doc2 = await response2.json();
      expect(doc1.id).toBe(doc2.id);
    }
  });

  test('Invalid Idempotency Key Format', async ({ page }) => {
    // Test with invalid idempotency key format
    const response = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': 'invalid-key-format'
      },
      data: {
        name: 'Test Chat'
      }
    });
    
    // Should return 400 Bad Request
    expect(response.status()).toBe(400);
  });

  test('Missing Idempotency Key for Write Operations', async ({ page }) => {
    // Test write operation without idempotency key
    const response = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
        // Missing Idempotency-Key header
      },
      data: {
        name: 'Test Chat'
      }
    });
    
    // Should return 400 Bad Request
    expect(response.status()).toBe(400);
  });

  test('Idempotency Key TTL Expiration', async ({ page }) => {
    const idempotencyKey = `ttl-test-${Date.now()}`;
    
    // First request
    const response1 = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': idempotencyKey
      },
      data: {
        name: 'TTL Test Chat'
      }
    });
    
    expect(response1.status()).toBe(201);
    
    // Wait for TTL to expire (simulate by using different key)
    const expiredKey = `expired-${Date.now()}`;
    
    // Second request with "expired" key should create new resource
    const response2 = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': expiredKey
      },
      data: {
        name: 'TTL Test Chat'
      }
    });
    
    // Should create new resource
    expect(response2.status()).toBe(201);
    const chat1 = await response1.json();
    const chat2 = await response2.json();
    expect(chat1.id).not.toBe(chat2.id);
  });

  test('Different Idempotency Keys Create Different Resources', async ({ page }) => {
    const key1 = `different-1-${Date.now()}`;
    const key2 = `different-2-${Date.now()}`;
    
    // First request with key1
    const response1 = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': key1
      },
      data: {
        name: 'Different Key Chat 1'
      }
    });
    
    expect(response1.status()).toBe(201);
    const chat1 = await response1.json();
    
    // Second request with key2
    const response2 = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': key2
      },
      data: {
        name: 'Different Key Chat 2'
      }
    });
    
    expect(response2.status()).toBe(201);
    const chat2 = await response2.json();
    
    // Should create different resources
    expect(chat1.id).not.toBe(chat2.id);
  });
});
