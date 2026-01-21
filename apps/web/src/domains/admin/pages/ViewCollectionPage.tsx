/**
 * ViewCollectionPage - View collection details in admin
 */
import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { collectionsApi } from '@shared/api/collections';
import { adminApi } from '@shared/api/admin';
import styles from './ViewCollectionPage.module.css';

export function ViewCollectionPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: collection, isLoading } = useQuery({
    queryKey: ['admin', 'collections', id],
    queryFn: () => collectionsApi.getById(id!),
    enabled: !!id,
  });

  const { data: tenantsData } = useQuery({
    queryKey: ['admin', 'tenants'],
    queryFn: () => adminApi.getTenants(),
  });

  const tenants = tenantsData?.items ?? [];
  const tenant = tenants.find(t => t.id === collection?.tenant_id);

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <Skeleton width={400} height={300} />
        </div>
      </div>
    );
  }

  if (!collection) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <div className={styles.emptyState}>
            <h2>Collection not found</h2>
            <Button onClick={() => navigate('/admin/collections')}>
              Back to Collections
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <Button
              variant="secondary"
              onClick={() => navigate('/admin/collections')}
            >
              ← Back
            </Button>
            <h1 className={styles.title}>{collection.name}</h1>
          </div>
        </div>

        <div className={styles.content}>
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Basic Information</h3>
            <div className={styles.grid}>
              <div className={styles.field}>
                <label>Slug</label>
                <div className={styles.value}>
                  <code>{collection.slug}</code>
                </div>
              </div>

              <div className={styles.field}>
                <label>Name</label>
                <div className={styles.value}>{collection.name}</div>
              </div>

              <div className={styles.field}>
                <label>Tenant</label>
                <div className={styles.value}>
                  {tenant ? (
                    <>
                      <strong>{tenant.name}</strong>
                      <br />
                      <small style={{ color: 'var(--text-secondary)' }}>
                        {tenant.id}
                      </small>
                    </>
                  ) : (
                    <code>{collection.tenant_id}</code>
                  )}
                </div>
              </div>

              <div className={styles.field}>
                <label>Search Capabilities</label>
                <div className={styles.value}>
                  <div className={styles.badges}>
                    <Badge tone="info" size="small">SQL</Badge>
                    {collection.has_vector_search && (
                      <Badge tone="warning" size="small">VECTOR</Badge>
                    )}
                  </div>
                </div>
              </div>

              <div className={styles.field}>
                <label>Status</label>
                <div className={styles.value}>
                  <Badge
                    tone={collection.is_active ? 'success' : 'neutral'}
                    size="small"
                  >
                    {collection.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              </div>

              <div className={styles.field}>
                <label>Row Count</label>
                <div className={styles.value}>
                  {collection.row_count.toLocaleString()}
                </div>
              </div>

              <div className={styles.field}>
                <label>Table Name</label>
                <div className={styles.value}>
                  <code>{collection.table_name || '—'}</code>
                </div>
              </div>

              <div className={styles.field}>
                <label>Created At</label>
                <div className={styles.value}>
                  {new Date(collection.created_at).toLocaleString()}
                </div>
              </div>

              <div className={styles.field}>
                <label>Updated At</label>
                <div className={styles.value}>
                  {new Date(collection.updated_at).toLocaleString()}
                </div>
              </div>
            </div>
          </div>

          {collection.description && (
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>Description</h3>
              <p className={styles.description}>{collection.description}</p>
            </div>
          )}

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>
              Fields ({collection.fields.length})
            </h3>
            <div className={styles.fieldsTable}>
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Required</th>
                    <th>Search Modes</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {collection.fields.map(field => (
                    <tr key={field.name}>
                      <td>
                        <code>{field.name}</code>
                      </td>
                      <td>
                        <Badge tone="neutral" size="small">
                          {field.type}
                        </Badge>
                      </td>
                      <td>
                        <Badge
                          tone={field.required ? 'warning' : 'neutral'}
                          size="small"
                        >
                          {field.required ? 'Yes' : 'No'}
                        </Badge>
                      </td>
                      <td>
                        <div className={styles.searchModesList}>
                          {field.search_modes?.map(mode => (
                            <Badge
                              key={mode}
                              tone={mode === 'vector' ? 'warning' : 'info'}
                              size="small"
                            >
                              {mode}
                            </Badge>
                          )) || <span>—</span>}
                        </div>
                      </td>
                      <td>{field.description || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ViewCollectionPage;
