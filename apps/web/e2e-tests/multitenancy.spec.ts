import { test, expect } from '@playwright/test';

test.describe('Multi-tenant E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin user
    await page.goto('/');
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'AdminPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('User in Multiple Tenants', async ({ page }) => {
    // Create first tenant
    await page.click('text=Tenant Management');
    await page.click('text=Create Tenant');
    await page.fill('input[name="tenantName"]', 'Tenant A');
    await page.click('button[type="submit"]');
    
    // Create second tenant
    await page.click('text=Create Tenant');
    await page.fill('input[name="tenantName"]', 'Tenant B');
    await page.click('button[type="submit"]');
    
    // Add user to both tenants
    await page.click('text=User Management');
    await page.fill('input[name="userEmail"]', 'multiuser@example.com');
    await page.selectOption('select[name="tenants"]', ['Tenant A', 'Tenant B']);
    await page.click('button[type="submit"]');
    
    // Verify user added to both tenants
    await expect(page.locator('text=User added to tenants successfully')).toBeVisible();
    
    // Login as the multi-tenant user
    await page.click('text=Logout');
    await page.fill('input[name="email"]', 'multiuser@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Should see tenant selector
    await expect(page.locator('text=Select Tenant')).toBeVisible();
    await expect(page.locator('text=Tenant A')).toBeVisible();
    await expect(page.locator('text=Tenant B')).toBeVisible();
  });

  test('Switching Between Tenants', async ({ page }) => {
    // Login as multi-tenant user
    await page.fill('input[name="email"]', 'multiuser@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Select Tenant A
    await page.click('text=Tenant A');
    await expect(page.locator('text=Current Tenant: Tenant A')).toBeVisible();
    
    // Create chat in Tenant A
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Tenant A Chat');
    await page.click('button[type="submit"]');
    
    // Switch to Tenant B
    await page.click('text=Switch Tenant');
    await page.click('text=Tenant B');
    await expect(page.locator('text=Current Tenant: Tenant B')).toBeVisible();
    
    // Should not see Tenant A chat
    await expect(page.locator('text=Tenant A Chat')).not.toBeVisible();
    
    // Create chat in Tenant B
    await page.click('text=New Chat');
    await page.fill('input[name="chatName"]', 'Tenant B Chat');
    await page.click('button[type="submit"]');
    
    // Switch back to Tenant A
    await page.click('text=Switch Tenant');
    await page.click('text=Tenant A');
    
    // Should see Tenant A chat but not Tenant B chat
    await expect(page.locator('text=Tenant A Chat')).toBeVisible();
    await expect(page.locator('text=Tenant B Chat')).not.toBeVisible();
  });

  test('Tenant-specific Data Isolation', async ({ page }) => {
    // Login as multi-tenant user
    await page.fill('input[name="email"]', 'multiuser@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    
    // Select Tenant A and upload document
    await page.click('text=Tenant A');
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const docA = new File(['Tenant A document content'], 'tenant-a-doc.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', docA);
    await page.fill('input[name="documentName"]', 'Tenant A Document');
    await page.click('button[type="submit"]');
    
    // Switch to Tenant B and upload different document
    await page.click('text=Switch Tenant');
    await page.click('text=Tenant B');
    await page.click('text=RAG Documents');
    await page.click('text=Upload Document');
    
    const docB = new File(['Tenant B document content'], 'tenant-b-doc.txt', { type: 'text/plain' });
    await page.setInputFiles('input[type="file"]', docB);
    await page.fill('input[name="documentName"]', 'Tenant B Document');
    await page.click('button[type="submit"]');
    
    // Verify isolation - Tenant B should not see Tenant A document
    await expect(page.locator('text=Tenant B Document')).toBeVisible();
    await expect(page.locator('text=Tenant A Document')).not.toBeVisible();
    
    // Switch back to Tenant A
    await page.click('text=Switch Tenant');
    await page.click('text=Tenant A');
    
    // Verify isolation - Tenant A should not see Tenant B document
    await expect(page.locator('text=Tenant A Document')).toBeVisible();
    await expect(page.locator('text=Tenant B Document')).not.toBeVisible();
  });

  test('Cross-tenant Operations Should Fail', async ({ page }) => {
    // Login as user in Tenant A
    await page.fill('input[name="email"]', 'tenantauser@example.com');
    await page.fill('input[name="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await page.click('text=Tenant A');
    
    // Test API calls with X-Tenant-Id header
    const response = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'tenant-b-id' // Wrong tenant ID
      }
    });
    
    // Should get 403 Forbidden for cross-tenant access
    expect(response.status()).toBe(403);
    
    // Test API calls without X-Tenant-Id header
    const noHeaderResponse = await page.request.get('/api/v1/chats');
    
    // Should get 400 Bad Request for missing tenant header
    expect(noHeaderResponse.status()).toBe(400);
    
    // Test API calls with invalid tenant ID format
    const invalidTenantResponse = await page.request.get('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'invalid-uuid-format'
      }
    });
    
    // Should get 400 Bad Request for invalid tenant format
    expect(invalidTenantResponse.status()).toBe(400);
    
    // Test creating resource with correct tenant ID
    const createResponse = await page.request.post('/api/v1/chats', {
      headers: {
        'X-Tenant-Id': 'tenant-a-id', // Correct tenant ID
        'Idempotency-Key': 'test-idempotency-key'
      },
      data: {
        name: 'Valid Tenant Chat'
      }
    });
    
    // Should succeed with correct tenant ID
    expect(createResponse.status()).toBe(201);
  });
});
