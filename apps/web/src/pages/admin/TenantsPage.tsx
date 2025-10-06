import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { tenantApi, type Tenant } from '@shared/api/tenant';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import styles from './TenantsPage.module.css';

export function TenantsPage() {
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // State
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  
  // Filters
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Load tenants
  const loadTenants = async () => {
    try {
      setLoading(true);
      const response = await tenantApi.getTenants({
        page,
        size: 20,
        search: search || undefined,
        is_active: statusFilter === 'all' ? undefined : statusFilter === 'active',
      });
      
      setTenants(response.tenants);
      setTotal(response.total);
      setHasMore(response.has_more);
    } catch (error) {
      showError('Failed to load tenants');
      console.error('Error loading tenants:', error);
    } finally {
      setLoading(false);
    }
  };

  // Load tenants on mount and when filters change
  useEffect(() => {
    loadTenants();
  }, [page, search, statusFilter]);

  // Handle search
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadTenants();
  };

  // Handle delete tenant
  const handleDeleteTenant = async (tenant: Tenant) => {
    if (!confirm(`Are you sure you want to delete tenant "${tenant.name}"?`)) {
      return;
    }

    try {
      await tenantApi.deleteTenant(tenant.id);
      showSuccess(`Tenant "${tenant.name}" deleted successfully`);
      loadTenants();
    } catch (error) {
      showError('Failed to delete tenant');
      console.error('Error deleting tenant:', error);
    }
  };

  // Handle status toggle
  const handleToggleStatus = async (tenant: Tenant) => {
    try {
      await tenantApi.updateTenant(tenant.id, {
        is_active: !tenant.is_active,
      });
      showSuccess(`Tenant "${tenant.name}" ${!tenant.is_active ? 'activated' : 'deactivated'}`);
      loadTenants();
    } catch (error) {
      showError('Failed to update tenant status');
      console.error('Error updating tenant:', error);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Tenants</h1>
          <p className={styles.pageDescription}>
            Manage tenant organizations and their settings
          </p>
        </div>
        <div className={styles.pageActions}>
          <Link to="/admin/tenants/new">
            <Button variant="primary">Create Tenant</Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className={styles.filters}>
        <form onSubmit={handleSearch} className={styles.searchForm}>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Search</label>
            <Input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tenants..."
              className={styles.filterInput}
            />
          </div>
          
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Status</label>
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className={styles.filterSelect}
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </div>

          <div className={styles.filterActions}>
            <Button type="submit" variant="secondary">
              Search
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setSearch('');
                setStatusFilter('all');
                setPage(1);
              }}
            >
              Clear
            </Button>
          </div>
        </form>
      </div>

      {/* Table */}
      <div className={styles.tableContainer}>
        <div className={styles.tableHeader}>
          <h2 className={styles.tableTitle}>Tenants</h2>
          <div className={styles.tableStats}>
            {total} tenant{total !== 1 ? 's' : ''} total
          </div>
        </div>

        <div className={styles.tableContent}>
          {loading ? (
            <div className={styles.loadingState}>
              <div className={styles.loadingSpinner}></div>
              <p>Loading tenants...</p>
            </div>
          ) : tenants.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateIcon}>🏢</div>
              <h3 className={styles.emptyStateTitle}>No tenants found</h3>
              <p className={styles.emptyStateDescription}>
                {search || statusFilter !== 'all'
                  ? 'No tenants match your current filters. Try adjusting your search criteria.'
                  : 'Get started by creating your first tenant organization.'}
              </p>
              <Link to="/admin/tenants/new">
                <Button variant="primary">Create First Tenant</Button>
              </Link>
            </div>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Description</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tenants.map((tenant) => (
                  <tr key={tenant.id}>
                    <td>
                      <div className={styles.tenantName}>
                        <strong>{tenant.name}</strong>
                        <span className={styles.tenantId}>ID: {tenant.id}</span>
                      </div>
                    </td>
                    <td>
                      <div className={styles.tenantDescription}>
                        {tenant.description || (
                          <span className={styles.noDescription}>No description</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        className={`${styles.status} ${
                          tenant.is_active ? styles.statusActive : styles.statusInactive
                        }`}
                      >
                        {tenant.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      <div className={styles.createdDate}>
                        {new Date(tenant.created_at).toLocaleDateString()}
                      </div>
                    </td>
                    <td>
                      <div className={styles.actions}>
                        <Link to={`/admin/tenants/${tenant.id}/edit`}>
                          <Button variant="outline" size="small">
                            Edit
                          </Button>
                        </Link>
                        <Button
                          variant="outline"
                          size="small"
                          onClick={() => handleToggleStatus(tenant)}
                        >
                          {tenant.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                        <Button
                          variant="danger"
                          size="small"
                          onClick={() => handleDeleteTenant(tenant)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {tenants.length > 0 && (
          <div className={styles.pagination}>
            <div className={styles.paginationInfo}>
              Showing {tenants.length} of {total} tenants
            </div>
            <div className={styles.paginationControls}>
              <Button
                variant="outline"
                size="small"
                onClick={() => setPage(page - 1)}
                disabled={page === 1}
              >
                Previous
              </Button>
              <span className={styles.pageNumber}>Page {page}</span>
              <Button
                variant="outline"
                size="small"
                onClick={() => setPage(page + 1)}
                disabled={!hasMore}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TenantsPage;
