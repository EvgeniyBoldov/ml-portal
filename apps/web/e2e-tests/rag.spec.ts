import { test, expect } from '@playwright/test';

test.describe('RAG E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Complete RAG Flow: Upload → Index → Search → Delete', async ({ page }) => {
    // Step 1: Upload document
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    // Create test file
    const testContent = 'This is a test document for RAG testing. It contains important information about machine learning and artificial intelligence.';
    const testFile = new File([testContent], 'test-document.txt', { type: 'text/plain' });
    
    // Upload file
    await page.setInputFiles('input[type="file"]', testFile);
    await page.fill('input[name="documentName"]', 'Test RAG Document');
    await page.click('button[type="submit"]');
    
    // Verify document uploaded
    await expect(page.locator('text=Document uploaded successfully')).toBeVisible();
    await expect(page.locator('text=Test RAG Document')).toBeVisible();
    
    // Step 2: Wait for indexing
    await expect(page.locator('text=Indexing...')).toBeVisible();
    await expect(page.locator('text=Indexed')).toBeVisible({ timeout: 30000 });
    
    // Step 3: Search documents
    await page.fill('input[name="searchQuery"]', 'machine learning');
    await page.click('button:has-text("Search")');
    
    // Verify search results
    await expect(page.locator('text=Test RAG Document')).toBeVisible();
    await expect(page.locator('text=machine learning')).toBeVisible();
    
    // Test semantic search
    await page.fill('input[name="searchQuery"]', 'artificial intelligence');
    await page.click('button:has-text("Semantic Search")');
    
    // Verify semantic search results
    await expect(page.locator('text=Test RAG Document')).toBeVisible();
    
    // Step 4: Delete document
    await page.click('button:has-text("Delete Document")');
    await page.click('button:has-text("Confirm")');
    
    // Verify document deleted
    await expect(page.locator('text=Document deleted successfully')).toBeVisible();
    await expect(page.locator('text=Test RAG Document')).not.toBeVisible();
  });

  test('Batch Document Processing', async ({ page }) => {
    await page.click('text=RAG Documents');
    await page.click('text=Batch Upload');
    
    // Create multiple test files
    const files = [
      new File(['Document 1 content about AI'], 'doc1.txt', { type: 'text/plain' }),
      new File(['Document 2 content about ML'], 'doc2.txt', { type: 'text/plain' }),
      new File(['Document 3 content about NLP'], 'doc3.txt', { type: 'text/plain' })
    ];
    
    // Upload multiple files
    await page.setInputFiles('input[type="file"]', files);
    await page.click('button[type="submit"]');
    
    // Verify batch upload success
    await expect(page.locator('text=3 documents uploaded successfully')).toBeVisible();
    
    // Wait for all documents to be indexed
    await expect(page.locator('text=Indexed').nth(2)).toBeVisible({ timeout: 60000 });
    
    // Verify all documents are visible
    await expect(page.locator('text=doc1.txt')).toBeVisible();
    await expect(page.locator('text=doc2.txt')).toBeVisible();
    await expect(page.locator('text=doc3.txt')).toBeVisible();
  });

  test('Search with Filters', async ({ page }) => {
    // Upload documents with different metadata
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const doc1 = new File(['AI research paper content'], 'ai-paper.pdf', { type: 'application/pdf' });
    await page.setInputFiles('input[type="file"]', doc1);
    await page.fill('input[name="documentName"]', 'AI Research Paper');
    await page.fill('input[name="category"]', 'Research');
    await page.fill('input[name="tags"]', 'AI, Research, Paper');
    await page.click('button[type="submit"]');
    
    const doc2 = new File(['ML tutorial content'], 'ml-tutorial.pdf', { type: 'application/pdf' });
    await page.setInputFiles('input[type="file"]', doc2);
    await page.fill('input[name="documentName"]', 'ML Tutorial');
    await page.fill('input[name="category"]', 'Tutorial');
    await page.fill('input[name="tags"]', 'ML, Tutorial, Education');
    await page.click('button[type="submit"]');
    
    // Wait for indexing
    await expect(page.locator('text=Indexed').nth(1)).toBeVisible({ timeout: 60000 });
    
    // Search with category filter
    await page.fill('input[name="searchQuery"]', 'AI');
    await page.selectOption('select[name="category"]', 'Research');
    await page.click('button:has-text("Search")');
    
    // Should only show AI Research Paper
    await expect(page.locator('text=AI Research Paper')).toBeVisible();
    await expect(page.locator('text=ML Tutorial')).not.toBeVisible();
    
    // Search with tag filter
    await page.fill('input[name="searchQuery"]', 'tutorial');
    await page.fill('input[name="tags"]', 'Tutorial');
    await page.click('button:has-text("Search")');
    
    // Should only show ML Tutorial
    await expect(page.locator('text=ML Tutorial')).toBeVisible();
    await expect(page.locator('text=AI Research Paper')).not.toBeVisible();
  });

  test('Document Versioning', async ({ page }) => {
    // Upload initial document
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const doc1 = new File(['Version 1 content'], 'document.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', doc1);
    await page.fill('input[name="documentName"]', 'Versioned Document');
    await page.click('button[type="submit"]');
    
    // Wait for indexing
    await expect(page.locator('text=Indexed')).toBeVisible({ timeout: 30000 });
    
    // Upload new version
    await page.click('button:has-text("Upload New Version")');
    const doc2 = new File(['Version 2 content with updates'], 'document.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', doc2);
    await page.click('button[type="submit"]');
    
    // Verify versioning
    await expect(page.locator('text=Version 2 uploaded successfully')).toBeVisible();
    await expect(page.locator('text=v2')).toBeVisible();
    
    // View version history
    await page.click('button:has-text("Version History")');
    await expect(page.locator('text=v1')).toBeVisible();
    await expect(page.locator('text=v2')).toBeVisible();
    
    // Revert to previous version
    await page.click('button:has-text("Revert to v1")');
    await page.click('button:has-text("Confirm")');
    
    // Verify reversion
    await expect(page.locator('text=Reverted to version 1')).toBeVisible();
  });
});
