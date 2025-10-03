import { test, expect } from '@playwright/test';

test.describe('Comprehensive RAG E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('Complete Document Lifecycle: Upload → Process → Index → Search → Update → Delete', async ({ page }) => {
    // Step 1: Upload document
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const documentContent = `
# Machine Learning Fundamentals

Machine learning is a subset of artificial intelligence that focuses on algorithms and statistical models.

## Types of Machine Learning

### Supervised Learning
Supervised learning uses labeled training data to learn a mapping function.

### Unsupervised Learning
Unsupervised learning finds hidden patterns in data without labeled examples.

### Reinforcement Learning
Reinforcement learning learns through interaction with an environment.

## Applications
- Image recognition
- Natural language processing
- Recommendation systems
- Autonomous vehicles
    `;
    
    const testFile = new File([documentContent], 'ml-fundamentals.md', { type: 'text/markdown' });
    await page.setInputFiles('input[type="file"]', testFile);
    await page.fill('input[name="documentName"]', 'ML Fundamentals Guide');
    await page.fill('input[name="category"]', 'Educational');
    await page.fill('input[name="tags"]', 'ML, AI, Education, Guide');
    await page.fill('textarea[name="description"]', 'Comprehensive guide to machine learning fundamentals');
    await page.click('button[type="submit"]');
    
    // Verify upload success
    await expect(page.locator('text=Document uploaded successfully')).toBeVisible();
    await expect(page.locator('text=ML Fundamentals Guide')).toBeVisible();
    
    // Step 2: Wait for processing and indexing
    await expect(page.locator('text=Processing...')).toBeVisible();
    await expect(page.locator('text=Indexing...')).toBeVisible();
    await expect(page.locator('text=Indexed')).toBeVisible({ timeout: 60000 });
    
    // Step 3: Search functionality
    await page.fill('input[name="searchQuery"]', 'supervised learning');
    await page.click('button:has-text("Search")');
    
    // Verify search results
    await expect(page.locator('text=ML Fundamentals Guide')).toBeVisible();
    await expect(page.locator('text=supervised learning')).toBeVisible();
    
    // Test semantic search
    await page.fill('input[name="searchQuery"]', 'learning algorithms');
    await page.click('button:has-text("Semantic Search")');
    
    // Verify semantic search results
    await expect(page.locator('text=ML Fundamentals Guide')).toBeVisible();
    
    // Test filtered search
    await page.fill('input[name="searchQuery"]', 'machine learning');
    await page.selectOption('select[name="category"]', 'Educational');
    await page.fill('input[name="tags"]', 'ML');
    await page.click('button:has-text("Filtered Search")');
    
    // Verify filtered results
    await expect(page.locator('text=ML Fundamentals Guide')).toBeVisible();
    
    // Step 4: Update document
    await page.click('button:has-text("Edit Document")');
    await page.fill('textarea[name="description"]', 'Updated comprehensive guide to machine learning fundamentals with advanced topics');
    await page.click('button[type="submit"]');
    
    // Verify update
    await expect(page.locator('text=Document updated successfully')).toBeVisible();
    
    // Step 5: Delete document
    await page.click('button:has-text("Delete Document")');
    await page.click('button:has-text("Confirm")');
    
    // Verify deletion
    await expect(page.locator('text=Document deleted successfully')).toBeVisible();
    await expect(page.locator('text=ML Fundamentals Guide')).not.toBeVisible();
  });

  test('Advanced Search Features: Vector Search → Hybrid Search → Contextual Search → Ranking', async ({ page }) => {
    // Upload multiple documents for testing
    const documents = [
      { name: 'AI Research Paper', content: 'Advanced artificial intelligence research on neural networks and deep learning algorithms.', category: 'Research' },
      { name: 'ML Tutorial', content: 'Machine learning tutorial covering supervised and unsupervised learning techniques.', category: 'Tutorial' },
      { name: 'Data Science Guide', content: 'Comprehensive data science guide including statistics, visualization, and analysis.', category: 'Guide' }
    ];
    
    for (const doc of documents) {
      await page.click('text=Upload Document');
      const testFile = new File([doc.content], `${doc.name}.txt`, { type: 'text/plain' });
      await page.setInputFiles('input[type="file"]', testFile);
      await page.fill('input[name="documentName"]', doc.name);
      await page.fill('input[name="category"]', doc.category);
      await page.click('button[type="submit"]');
      await expect(page.locator('text=Document uploaded successfully')).toBeVisible();
    }
    
    // Wait for all documents to be indexed
    await expect(page.locator('text=Indexed').nth(2)).toBeVisible({ timeout: 90000 });
    
    // Test vector similarity search
    await page.fill('input[name="searchQuery"]', 'neural networks');
    await page.click('button:has-text("Vector Search")');
    
    // Should find AI Research Paper first (most similar)
    await expect(page.locator('text=AI Research Paper')).toBeVisible();
    
    // Test hybrid search (vector + text)
    await page.fill('input[name="searchQuery"]', 'learning algorithms');
    await page.click('button:has-text("Hybrid Search")');
    
    // Should find both AI Research Paper and ML Tutorial
    await expect(page.locator('text=AI Research Paper')).toBeVisible();
    await expect(page.locator('text=ML Tutorial')).toBeVisible();
    
    // Test contextual search with conversation history
    await page.click('text=Chat');
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'RAG Search Test');
    await page.click('button[type="submit"]');
    
    // Add context to conversation
    await page.fill('textarea[name="message"]', 'I need information about machine learning');
    await page.click('button:has-text("Send")');
    
    // Use contextual search
    await page.click('text=RAG Documents');
    await page.fill('input[name="searchQuery"]', 'supervised learning');
    await page.click('button:has-text("Contextual Search")');
    
    // Should prioritize ML Tutorial based on context
    await expect(page.locator('text=ML Tutorial')).toBeVisible();
    
    // Test search ranking
    await page.fill('input[name="searchQuery"]', 'data analysis');
    await page.click('button:has-text("Search")');
    
    // Should rank Data Science Guide highest
    const results = page.locator('[data-testid="search-result"]');
    await expect(results.nth(0)).toContainText('Data Science Guide');
  });

  test('Document Management: Versioning → Collaboration → Permissions → Analytics', async ({ page }) => {
    // Upload initial document
    await page.click('text=Upload Document');
    const doc1 = new File(['Version 1: Basic ML concepts'], 'ml-doc.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', doc1);
    await page.fill('input[name="documentName"]', 'ML Documentation');
    await page.click('button[type="submit"]');
    
    // Wait for indexing
    await expect(page.locator('text=Indexed')).toBeVisible({ timeout: 30000 });
    
    // Upload new version
    await page.click('button:has-text("Upload New Version")');
    const doc2 = new File(['Version 2: Advanced ML concepts with deep learning'], 'ml-doc.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', doc2);
    await page.click('button[type="submit"]');
    
    // Verify versioning
    await expect(page.locator('text=Version 2 uploaded successfully')).toBeVisible();
    await expect(page.locator('text=v2')).toBeVisible();
    
    // View version history
    await page.click('button:has-text("Version History")');
    await expect(page.locator('text=v1')).toBeVisible();
    await expect(page.locator('text=v2')).toBeVisible();
    
    // Test collaboration features
    await page.click('button:has-text("Share Document")');
    await page.fill('input[name="collaboratorEmail"]', 'collaborator@example.com');
    await page.selectOption('select[name="permission"]', 'edit');
    await page.click('button[type="submit"]');
    
    // Verify collaboration invitation
    await expect(page.locator('text=Collaboration invitation sent')).toBeVisible();
    
    // Test permissions
    await page.click('button:has-text("Manage Permissions")');
    await expect(page.locator('text=Document Permissions')).toBeVisible();
    await expect(page.locator('text=Owner: test@example.com')).toBeVisible();
    await expect(page.locator('text=Collaborator: collaborator@example.com')).toBeVisible();
    
    // View document analytics
    await page.click('button:has-text("View Analytics")');
    await expect(page.locator('text=Document Analytics')).toBeVisible();
    await expect(page.locator('text=View Count')).toBeVisible();
    await expect(page.locator('text=Search Count')).toBeVisible();
    await expect(page.locator('text=Last Accessed')).toBeVisible();
  });

  test('Performance and Scalability: Large Documents → Batch Processing → Concurrent Searches → Memory Usage', async ({ page }) => {
    // Test large document upload
    const largeContent = 'Large document content. '.repeat(10000); // ~200KB document
    const largeFile = new File([largeContent], 'large-document.txt', { type: 'text/plain' });
    
    await page.click('text=Upload Document');
    await page.setInputFiles('input[type="file"]', largeFile);
    await page.fill('input[name="documentName"]', 'Large Document');
    await page.click('button[type="submit"]');
    
    // Should show progress indicator for large files
    await expect(page.locator('text=Processing large document...')).toBeVisible();
    await expect(page.locator('text=Document uploaded successfully')).toBeVisible({ timeout: 120000 });
    
    // Test batch document processing
    await page.click('text=Batch Upload');
    const batchFiles = Array.from({ length: 10 }, (_, i) => 
      new File([`Document ${i + 1} content`], `batch-doc-${i + 1}.txt`, { type: 'text/plain' })
    );
    
    await page.setInputFiles('input[type="file"]', batchFiles);
    await page.click('button[type="submit"]');
    
    // Should show batch progress
    await expect(page.locator('text=Processing 10 documents...')).toBeVisible();
    await expect(page.locator('text=10 documents uploaded successfully')).toBeVisible({ timeout: 180000 });
    
    // Test concurrent searches
    const searchPromises = Array.from({ length: 5 }, (_, i) => 
      page.fill('input[name="searchQuery"]', `search query ${i}`).then(() => 
        page.click('button:has-text("Search")')
      )
    );
    
    await Promise.all(searchPromises);
    
    // All searches should complete successfully
    await expect(page.locator('text=Search results')).toBeVisible();
    
    // Test memory usage monitoring
    await page.click('text=System Status');
    await expect(page.locator('text=Memory Usage')).toBeVisible();
    await expect(page.locator('text=Index Size')).toBeVisible();
    await expect(page.locator('text=Document Count')).toBeVisible();
  });
});
