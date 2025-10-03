import { test, expect } from '@playwright/test';

test.describe('Performance E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Page Load Performance', async ({ page }) => {
    // Test dashboard load time
    const startTime = Date.now();
    await page.goto('/dashboard');
    await expect(page.locator('text=Dashboard')).toBeVisible();
    const loadTime = Date.now() - startTime;
    
    // Should load within 2 seconds
    expect(loadTime).toBeLessThan(2000);
    
    // Test chat page load time
    const chatStartTime = Date.now();
    await page.goto('/chats');
    await expect(page.locator('text=Chats')).toBeVisible();
    const chatLoadTime = Date.now() - chatStartTime;
    
    // Should load within 2 seconds
    expect(chatLoadTime).toBeLessThan(2000);
  });

  test('API Response Times', async ({ page }) => {
    // Test auth endpoint performance
    const authStartTime = Date.now();
    const authResponse = await page.request.get('/api/v1/auth/me', {
      headers: {
        'Authorization': `Bearer ${await page.evaluate(() => localStorage.getItem('access_token'))}`
      }
    });
    const authTime = Date.now() - authStartTime;
    
    expect(authResponse.status()).toBe(200);
    expect(authTime).toBeLessThan(500); // Should respond within 500ms
    
    // Test chat list performance
    const chatStartTime = Date.now();
    const chatResponse = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 20
      }
    });
    const chatTime = Date.now() - chatStartTime;
    
    expect(chatResponse.status()).toBe(200);
    expect(chatTime).toBeLessThan(1000); // Should respond within 1 second
    
    // Test document list performance
    const docStartTime = Date.now();
    const docResponse = await page.request.get('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 20
      }
    });
    const docTime = Date.now() - docStartTime;
    
    expect(docResponse.status()).toBe(200);
    expect(docTime).toBeLessThan(1000); // Should respond within 1 second
  });

  test('Concurrent API Requests', async ({ page }) => {
    const tenantId = 'test-tenant-id';
    
    // Make multiple concurrent requests
    const promises = [];
    for (let i = 0; i < 10; i++) {
      promises.push(
        page.request.get('/api/v1/chats', {
          headers: {
            'X-Tenant-Id': tenantId
          },
          params: {
            limit: 10
          }
        })
      );
    }
    
    const startTime = Date.now();
    const responses = await Promise.all(promises);
    const totalTime = Date.now() - startTime;
    
    // All requests should succeed
    responses.forEach(response => {
      expect(response.status()).toBe(200);
    });
    
    // Should complete within 3 seconds
    expect(totalTime).toBeLessThan(3000);
  });

  test('Large Payload Handling', async ({ page }) => {
    // Create a chat with a large message
    const chatResponse = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `large-payload-${Date.now()}`
      },
      data: {
        name: 'Large Payload Test'
      }
    });
    
    const chat = await chatResponse.json();
    
    // Send a large message (10KB)
    const largeMessage = 'A'.repeat(10000);
    const startTime = Date.now();
    
    const messageResponse = await page.request.post(`/api/v1/chats/${chat.id}/messages`, {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `large-msg-${Date.now()}`
      },
      data: {
        content: largeMessage,
        role: 'user'
      }
    });
    
    const responseTime = Date.now() - startTime;
    
    expect(messageResponse.status()).toBe(201);
    expect(responseTime).toBeLessThan(2000); // Should handle large payload within 2 seconds
  });

  test('Memory Usage Stability', async ({ page }) => {
    // Perform multiple operations to test memory stability
    const operations = [];
    
    for (let i = 0; i < 50; i++) {
      operations.push(
        page.request.get('/api/v1/chats', {
          headers: {
            'X-Tenant-Id': 'test-tenant-id'
          },
          params: {
            limit: 10
          }
        })
      );
    }
    
    // Execute all operations
    const responses = await Promise.all(operations);
    
    // All should succeed
    responses.forEach(response => {
      expect(response.status()).toBe(200);
    });
    
    // Check if page is still responsive
    await page.goto('/dashboard');
    await expect(page.locator('text=Dashboard')).toBeVisible();
  });

  test('Database Query Performance', async ({ page }) => {
    // Test pagination performance with large datasets
    const startTime = Date.now();
    
    const response = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        limit: 100,
        cursor: null
      }
    });
    
    const queryTime = Date.now() - startTime;
    
    expect(response.status()).toBe(200);
    expect(queryTime).toBeLessThan(1500); // Should query within 1.5 seconds
    
    const data = await response.json();
    expect(data.items.length).toBeLessThanOrEqual(100);
  });

  test('File Upload Performance', async ({ page }) => {
    // Test file upload performance
    const testFile = new File(['Test content'], 'performance-test.txt', { type: 'text/plain' });
    
    const startTime = Date.now();
    
    const uploadResponse = await page.request.post('/api/v1/rag/documents', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id',
        'Idempotency-Key': `upload-perf-${Date.now()}`
      },
      data: {
        filename: 'performance-test.txt',
        title: 'Performance Test Document',
        content_type: 'text/plain',
        size: testFile.size
      }
    });
    
    const uploadTime = Date.now() - startTime;
    
    expect(uploadResponse.status()).toBe(201);
    expect(uploadTime).toBeLessThan(2000); // Should upload within 2 seconds
  });

  test('Search Performance', async ({ page }) => {
    // Test search performance
    const startTime = Date.now();
    
    const searchResponse = await page.request.get('/api/v1/rag/search', {
      headers: {
        'X-Tenant-Id': 'test-tenant-id'
      },
      params: {
        query: 'test search query',
        limit: 20
      }
    });
    
    const searchTime = Date.now() - startTime;
    
    expect(searchResponse.status()).toBe(200);
    expect(searchTime).toBeLessThan(2000); // Should search within 2 seconds
  });

  test('WebSocket Connection Performance', async ({ page }) => {
    // Test WebSocket connection establishment time
    const startTime = Date.now();
    
    await page.evaluate(async () => {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket('ws://localhost:8000/ws');
        
        ws.onopen = () => {
          resolve(Date.now());
          ws.close();
        };
        
        ws.onerror = reject;
        
        setTimeout(() => reject(new Error('Connection timeout')), 5000);
      });
    });
    
    const connectionTime = Date.now() - startTime;
    
    expect(connectionTime).toBeLessThan(1000); // Should connect within 1 second
  });

  test('Resource Loading Performance', async ({ page }) => {
    // Test static resource loading
    const startTime = Date.now();
    
    // Load CSS
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const loadTime = Date.now() - startTime;
    
    // Should load all resources within 3 seconds
    expect(loadTime).toBeLessThan(3000);
    
    // Check for any failed resource loads
    const failedResources = await page.evaluate(() => {
      return performance.getEntriesByType('resource')
        .filter(entry => entry.transferSize === 0 && entry.decodedBodySize === 0)
        .length;
    });
    
    expect(failedResources).toBe(0);
  });
});
