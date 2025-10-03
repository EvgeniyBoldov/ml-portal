import { test, expect } from '@playwright/test';

test.describe('Chat E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Complete Chat Flow: Create → Add Messages → Search → Delete', async ({ page }) => {
    // Step 1: Create chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', `Test Chat ${Date.now()}`);
    await page.click('button[type="submit"]');
    
    // Verify chat created
    await expect(page.locator('text=Test Chat')).toBeVisible();
    
    // Step 2: Add messages
    const chatInput = page.locator('textarea[name="message"]');
    await chatInput.fill('Hello, this is a test message');
    await page.click('button:has-text("Send")');
    
    // Verify message sent
    await expect(page.locator('text=Hello, this is a test message')).toBeVisible();
    
    // Add another message
    await chatInput.fill('This is another test message');
    await page.click('button:has-text("Send")');
    
    // Verify second message
    await expect(page.locator('text=This is another test message')).toBeVisible();
    
    // Step 3: Search messages
    await page.fill('input[name="search"]', 'test message');
    await page.click('button:has-text("Search")');
    
    // Verify search results
    await expect(page.locator('text=Hello, this is a test message')).toBeVisible();
    await expect(page.locator('text=This is another test message')).toBeVisible();
    
    // Step 4: Delete chat
    await page.click('button:has-text("Delete Chat")');
    await page.click('button:has-text("Confirm")');
    
    // Verify chat deleted
    await expect(page.locator('text=Test Chat')).not.toBeVisible();
  });

  test('Multi-user Chat', async ({ page, browser }) => {
    // Create chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Multi-user Chat');
    await page.click('button[type="submit"]');
    
    // Add first user to chat
    await page.click('text=Add User');
    await page.fill('input[name="userEmail"]', 'user2@example.com');
    await page.click('button[type="submit"]');
    
    // Verify user added
    await expect(page.locator('text=user2@example.com')).toBeVisible();
    
    // Open second browser context for second user
    const context2 = await browser.newContext();
    const page2 = await context2.newPage();
    
    // Login as second user
    await page2.goto('/');
    await page2.fill('input[name="email"]', 'user2@example.com');
    await page2.fill('input[name="password"]', 'TestPassword123!');
    await page2.click('button[type="submit"]');
    
    // Second user should see the chat
    await expect(page2.locator('text=Multi-user Chat')).toBeVisible();
    
    // Send message from first user
    await page.fill('textarea[name="message"]', 'Message from user 1');
    await page.click('button:has-text("Send")');
    
    // Second user should see the message
    await expect(page2.locator('text=Message from user 1')).toBeVisible();
    
    // Send message from second user
    await page2.fill('textarea[name="message"]', 'Message from user 2');
    await page2.click('button:has-text("Send")');
    
    // First user should see the message
    await expect(page.locator('text=Message from user 2')).toBeVisible();
    
    await context2.close();
  });

  test('Chat Sharing', async ({ page }) => {
    // Create chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Shared Chat');
    await page.click('button[type="submit"]');
    
    // Add message
    await page.fill('textarea[name="message"]', 'This is a shared message');
    await page.click('button:has-text("Send")');
    
    // Share chat
    await page.click('text=Share Chat');
    const shareUrl = await page.inputValue('input[name="shareUrl"]');
    
    // Verify share URL is generated
    expect(shareUrl).toContain('/chat/');
    
    // Open shared chat in new tab
    await page.goto(shareUrl);
    
    // Verify shared chat is accessible
    await expect(page.locator('text=Shared Chat')).toBeVisible();
    await expect(page.locator('text=This is a shared message')).toBeVisible();
  });

  test('Chat Archiving', async ({ page }) => {
    // Create chat
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Archive Test Chat');
    await page.click('button[type="submit"]');
    
    // Add message
    await page.fill('textarea[name="message"]', 'This chat will be archived');
    await page.click('button:has-text("Send")');
    
    // Archive chat
    await page.click('button:has-text("Archive Chat")');
    await page.click('button:has-text("Confirm")');
    
    // Verify chat is archived
    await expect(page.locator('text=Chat archived successfully')).toBeVisible();
    
    // Switch to archived chats view
    await page.click('text=Archived Chats');
    
    // Verify archived chat is visible
    await expect(page.locator('text=Archive Test Chat')).toBeVisible();
    
    // Restore chat
    await page.click('button:has-text("Restore")');
    
    // Verify chat is restored
    await expect(page.locator('text=Chat restored successfully')).toBeVisible();
  });
});
