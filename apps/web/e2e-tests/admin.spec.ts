import { test, expect } from '@playwright/test';

test.describe('Admin E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin user
    await page.goto('/');
    await page.fill('input[name="email"]', 'admin@example.com');
    await page.fill('input[name="password"]', 'AdminPassword123!');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Admin Dashboard')).toBeVisible();
  });

  test('User Management', async ({ page }) => {
    // Navigate to user management
    await page.click('text=User Management');
    
    // View all users
    await expect(page.locator('text=All Users')).toBeVisible();
    
    // Create new user
    await page.click('text=Create User');
    await page.fill('input[name="email"]', `newuser_${Date.now()}@example.com`);
    await page.fill('input[name="password"]', 'NewUserPassword123!');
    await page.selectOption('select[name="role"]', 'reader');
    await page.click('button[type="submit"]');
    
    // Verify user created
    await expect(page.locator('text=User created successfully')).toBeVisible();
    
    // Edit user
    await page.click('button:has-text("Edit")');
    await page.selectOption('select[name="role"]', 'writer');
    await page.click('button[type="submit"]');
    
    // Verify user updated
    await expect(page.locator('text=User updated successfully')).toBeVisible();
    
    // Deactivate user
    await page.click('button:has-text("Deactivate")');
    await page.click('button:has-text("Confirm")');
    
    // Verify user deactivated
    await expect(page.locator('text=User deactivated successfully')).toBeVisible();
  });

  test('Tenant Management', async ({ page }) => {
    // Navigate to tenant management
    await page.click('text=Tenant Management');
    
    // View all tenants
    await expect(page.locator('text=All Tenants')).toBeVisible();
    
    // Create new tenant
    await page.click('text=Create Tenant');
    await page.fill('input[name="tenantName"]', `New Tenant ${Date.now()}`);
    await page.fill('input[name="description"]', 'Test tenant description');
    await page.click('button[type="submit"]');
    
    // Verify tenant created
    await expect(page.locator('text=Tenant created successfully')).toBeVisible();
    
    // Edit tenant
    await page.click('button:has-text("Edit")');
    await page.fill('input[name="description"]', 'Updated tenant description');
    await page.click('button[type="submit"]');
    
    // Verify tenant updated
    await expect(page.locator('text=Tenant updated successfully')).toBeVisible();
    
    // Add user to tenant
    await page.click('button:has-text("Manage Users")');
    await page.fill('input[name="userEmail"]', 'test@example.com');
    await page.click('button[type="submit"]');
    
    // Verify user added
    await expect(page.locator('text=User added to tenant successfully')).toBeVisible();
    
    // Remove user from tenant
    await page.click('button:has-text("Remove")');
    await page.click('button:has-text("Confirm")');
    
    // Verify user removed
    await expect(page.locator('text=User removed from tenant successfully')).toBeVisible();
  });

  test('System Monitoring', async ({ page }) => {
    // Navigate to system monitoring
    await page.click('text=System Monitoring');
    
    // View system metrics
    await expect(page.locator('text=System Metrics')).toBeVisible();
    await expect(page.locator('text=Active Users')).toBeVisible();
    await expect(page.locator('text=Total Tenants')).toBeVisible();
    await expect(page.locator('text=Database Status')).toBeVisible();
    
    // View API metrics
    await page.click('text=API Metrics');
    await expect(page.locator('text=Request Count')).toBeVisible();
    await expect(page.locator('text=Response Time')).toBeVisible();
    await expect(page.locator('text=Error Rate')).toBeVisible();
    
    // View resource usage
    await page.click('text=Resource Usage');
    await expect(page.locator('text=CPU Usage')).toBeVisible();
    await expect(page.locator('text=Memory Usage')).toBeVisible();
    await expect(page.locator('text=Disk Usage')).toBeVisible();
    
    // View logs
    await page.click('text=System Logs');
    await expect(page.locator('text=Application Logs')).toBeVisible();
    await expect(page.locator('text=Error Logs')).toBeVisible();
    await expect(page.locator('text=Access Logs')).toBeVisible();
  });

  test('Bulk Operations', async ({ page }) => {
    // Navigate to bulk operations
    await page.click('text=Bulk Operations');
    
    // Bulk user creation
    await page.click('text=Bulk Create Users');
    const csvContent = `email,password,role
bulk1@example.com,Password123!,reader
bulk2@example.com,Password123!,writer
bulk3@example.com,Password123!,admin`;
    
    const csvFile = new File([csvContent], 'users.csv', { type: 'text/csv' });
    await page.setInputFiles('input[type="file"]', csvFile);
    await page.click('button[type="submit"]');
    
    // Verify bulk creation
    await expect(page.locator('text=3 users created successfully')).toBeVisible();
    
    // Bulk tenant assignment
    await page.click('text=Bulk Assign Tenants');
    const assignmentData = {
      tenantId: 'tenant-1',
      userIds: ['bulk1@example.com', 'bulk2@example.com']
    };
    
    await page.fill('textarea[name="assignmentData"]', JSON.stringify(assignmentData));
    await page.click('button[type="submit"]');
    
    // Verify bulk assignment
    await expect(page.locator('text=2 users assigned to tenant successfully')).toBeVisible();
    
    // Bulk user deactivation
    await page.click('text=Bulk Deactivate Users');
    await page.fill('textarea[name="userEmails"]', 'bulk1@example.com\nbulk2@example.com');
    await page.click('button[type="submit"]');
    
    // Verify bulk deactivation
    await expect(page.locator('text=2 users deactivated successfully')).toBeVisible();
  });
});
