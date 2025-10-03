import { test, expect } from '@playwright/test';

test.describe('Error Recovery E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Network Failures', async ({ page }) => {
    // Start creating a chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Network Test Chat');
    
    // Simulate network failure
    await page.route('**/api/v1/chats', route => route.abort());
    
    await page.click('button[type="submit"]');
    
    // Should show error message
    await expect(page.locator('text=Network error. Please try again.')).toBeVisible();
    
    // Should show retry button
    await expect(page.locator('button:has-text("Retry")')).toBeVisible();
    
    // Restore network and retry
    await page.unroute('**/api/v1/chats');
    await page.click('button:has-text("Retry")');
    
    // Should succeed on retry
    await expect(page.locator('text=Chat created successfully')).toBeVisible();
  });

  test('Database Failures', async ({ page }) => {
    // Start uploading a document
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const testFile = new File(['Test document content'], 'test.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', testFile);
    await page.fill('input[name="documentName"]', 'Database Test Document');
    
    // Simulate database failure
    await page.route('**/api/v1/documents', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Database connection failed' })
      });
    });
    
    await page.click('button[type="submit"]');
    
    // Should show database error message
    await expect(page.locator('text=Database error. Please try again later.')).toBeVisible();
    
    // Should show graceful degradation message
    await expect(page.locator('text=Some features may be temporarily unavailable')).toBeVisible();
  });

  test('External Service Failures', async ({ page }) => {
    // Try to use RAG search
    await page.click('text=RAG Documents');
    await page.fill('input[name="searchQuery"]', 'test query');
    
    // Simulate Qdrant failure
    await page.route('**/api/v1/search', route => {
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Vector database unavailable' })
      });
    });
    
    await page.click('button:has-text("Search")');
    
    // Should show external service error
    await expect(page.locator('text=Search service temporarily unavailable')).toBeVisible();
    
    // Should offer fallback options
    await expect(page.locator('text=Try text search instead')).toBeVisible();
    
    // Try fallback search
    await page.click('text=Try text search instead');
    
    // Should work with fallback
    await expect(page.locator('text=Search results')).toBeVisible();
  });

  test('Graceful Degradation', async ({ page }) => {
    // Simulate partial service failure
    await page.route('**/api/v1/chats', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ 
          chats: [],
          warning: 'Chat service running in limited mode'
        })
      });
    });
    
    // Navigate to chats
    await page.click('text=Chats');
    
    // Should show degraded mode warning
    await expect(page.locator('text=Running in limited mode')).toBeVisible();
    
    // Should still show basic functionality
    await expect(page.locator('text=Chats')).toBeVisible();
    
    // Should show what features are available
    await expect(page.locator('text=Available features')).toBeVisible();
  });

  test('Session Recovery', async ({ page }) => {
    // Create some data
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Session Recovery Chat');
    await page.click('button[type="submit"]');
    
    // Simulate session expiry
    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    });
    
    // Try to perform action
    await page.fill('textarea[name="message"]', 'Test message');
    await page.click('button:has-text("Send")');
    
    // Should redirect to login
    await expect(page.locator('text=Login')).toBeVisible();
    
    // Should preserve the chat data
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Should return to the chat
    await expect(page.locator('text=Session Recovery Chat')).toBeVisible();
  });

  test('Data Consistency Recovery', async ({ page }) => {
    // Create chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Consistency Test Chat');
    await page.click('button[type="submit"]');
    
    // Add message
    await page.fill('textarea[name="message"]', 'Test message');
    await page.click('button:has-text("Send")');
    
    // Simulate partial failure during message send
    await page.route('**/api/v1/chats/*/messages', route => {
      // Simulate timeout
      setTimeout(() => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ message: 'Message sent' })
        });
      }, 10000);
    });
    
    await page.fill('textarea[name="message"]', 'Timeout test message');
    await page.click('button:has-text("Send")');
    
    // Should show loading state
    await expect(page.locator('text=Sending...')).toBeVisible();
    
    // Should eventually succeed or show retry option
    await expect(page.locator('text=Message sent').or(page.locator('button:has-text("Retry")'))).toBeVisible({ timeout: 15000 });
  });
});
