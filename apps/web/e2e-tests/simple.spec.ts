import { test, expect } from '@playwright/test';

test.describe('Simple E2E Tests', () => {
  test('Basic Application Flow', async ({ page }) => {
    // Navigate to home page
    await page.goto('/');
    
    // Should show login page
    await expect(page.locator('text=Login')).toBeVisible();
    
    // Login
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Should show dashboard
    await expect(page.locator('text=Dashboard')).toBeVisible();
    
    // Navigate to different sections
    await page.click('text=Chats');
    await expect(page.locator('text=Chats')).toBeVisible();
    
    await page.click('text=RAG Documents');
    await expect(page.locator('text=RAG Documents')).toBeVisible();
    
    await page.click('text=Profile');
    await expect(page.locator('text=Profile')).toBeVisible();
  });

  test('Basic Chat Functionality', async ({ page }) => {
    // Login
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Create new chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Simple Test Chat');
    await page.click('button[type="submit"]');
    
    // Send message
    await page.fill('textarea[name="message"]', 'Hello, this is a test message');
    await page.click('button:has-text("Send")');
    
    // Verify message appears
    await expect(page.locator('text=Hello, this is a test message')).toBeVisible();
  });

  test('Basic Document Upload', async ({ page }) => {
    // Login
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Upload document
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const testFile = new File(['Simple test document content'], 'test.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', testFile);
    await page.fill('input[name="documentName"]', 'Simple Test Document');
    await page.click('button[type="submit"]');
    
    // Verify upload success
    await expect(page.locator('text=Document uploaded successfully')).toBeVisible();
    await expect(page.locator('text=Simple Test Document')).toBeVisible();
  });

  test('Basic Search Functionality', async ({ page }) => {
    // Login
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Perform search
    await page.click('text=RAG Documents');
    await page.fill('input[name="searchQuery"]', 'test');
    await page.click('button:has-text("Search")');
    
    // Should show search results or no results message
    await expect(page.locator('text=Search results').or(page.locator('text=No results found'))).toBeVisible();
  });

  test('User Profile Access', async ({ page }) => {
    // Login
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Access profile
    await page.click('text=Profile');
    
    // Should show profile information
    await expect(page.locator('text=Profile')).toBeVisible();
    await expect(page.locator('text=Email')).toBeVisible();
    await expect(page.locator('text=test@example.com')).toBeVisible();
  });

  test('Logout Functionality', async ({ page }) => {
    // Login
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Verify logged in
    await expect(page.locator('text=Dashboard')).toBeVisible();
    
    // Logout
    await page.click('text=Logout');
    
    // Should return to login page
    await expect(page.locator('text=Login')).toBeVisible();
    
    // Try to access protected page
    await page.goto('/dashboard');
    await expect(page.locator('text=Please login to continue')).toBeVisible();
  });
});
