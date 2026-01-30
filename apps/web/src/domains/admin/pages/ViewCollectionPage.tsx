/**
 * ViewCollectionPage - View collection details in admin
 * 
 * Uses EntityPage pattern for consistency
 */
import React from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Badge from '@shared/ui/Badge';
import { EntityPage } from '@shared/ui/EntityPage';
import { ContentBlock, ContentGrid } from '@shared/ui/ContentBlock';
import { DataTable, type DataTableColumn } from '@shared/ui/DataTable';
import { collectionsApi } from '@shared/api/collections';
import { adminApi } from '@shared/api/admin';

interface CollectionField {
  name: string;
  type: string;
  required: boolean;
  search_modes?: string[];
  description?: string;
}

export function ViewCollectionPage() {
  const { id } = useParams<{ id: string }>();

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

  const fieldColumns: DataTableColumn<CollectionField>[] = [
    {
      key: 'name',
      label: 'Поле',
      render: (row) => <code style={{ fontSize: '0.875rem' }}>{row.name}</code>,
    },
    {
      key: 'type',
      label: 'Тип',
      width: 100,
      render: (row) => <Badge variant="default">{row.type}</Badge>,
    },
    {
      key: 'required',
      label: 'Обязательное',
      width: 120,
      render: (row) => (
        <Badge variant={row.required ? 'warning' : 'default'}>
          {row.required ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'search_modes',
      label: 'Режимы поиска',
      width: 150,
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.search_modes?.map(mode => (
            <Badge key={mode} variant={mode === 'vector' ? 'warning' : 'info'}>
              {mode}
            </Badge>
          )) || '—'}
        </div>
      ),
    },
    {
      key: 'description',
      label: 'Описание',
      render: (row) => row.description || '—',
    },
  ];

  return (
    <EntityPage
      mode="view"
      entityName={collection?.name || 'Коллекция'}
      entityTypeLabel="коллекции"
      backPath="/admin/collections"
      loading={isLoading}
    >
      <ContentGrid>
        {/* Basic Info - 2/3 */}
        <ContentBlock
          width="2/3"
          title="Основная информация"
          icon="database"
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Slug</label>
              <div style={{ marginTop: '0.25rem' }}><code>{collection?.slug}</code></div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Название</label>
              <div style={{ marginTop: '0.25rem' }}>{collection?.name}</div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Тенант</label>
              <div style={{ marginTop: '0.25rem' }}>
                {tenant ? tenant.name : collection?.tenant_id}
              </div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Таблица</label>
              <div style={{ marginTop: '0.25rem' }}><code>{collection?.table_name || '—'}</code></div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Записей</label>
              <div style={{ marginTop: '0.25rem' }}>{collection?.row_count?.toLocaleString() || 0}</div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Создана</label>
              <div style={{ marginTop: '0.25rem' }}>
                {collection?.created_at ? new Date(collection.created_at).toLocaleString('ru-RU') : '—'}
              </div>
            </div>
          </div>
          {collection?.description && (
            <div style={{ marginTop: '1rem' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Описание</label>
              <p style={{ marginTop: '0.25rem', color: 'var(--color-text-muted)' }}>{collection.description}</p>
            </div>
          )}
        </ContentBlock>

        {/* Status - 1/3 */}
        <ContentBlock
          width="1/3"
          title="Статус и возможности"
          icon="shield"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Статус</label>
              <div style={{ marginTop: '0.25rem' }}>
                <Badge variant={collection?.is_active ? 'success' : 'default'}>
                  {collection?.is_active ? 'Активна' : 'Неактивна'}
                </Badge>
              </div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Поиск</label>
              <div style={{ marginTop: '0.25rem', display: 'flex', gap: '0.5rem' }}>
                <Badge variant="info">SQL</Badge>
                {collection?.has_vector_search && <Badge variant="warning">VECTOR</Badge>}
              </div>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Обновлена</label>
              <div style={{ marginTop: '0.25rem' }}>
                {collection?.updated_at ? new Date(collection.updated_at).toLocaleString('ru-RU') : '—'}
              </div>
            </div>
          </div>
        </ContentBlock>

        {/* Fields Table - full width */}
        <ContentBlock
          width="full"
          title={`Поля (${collection?.fields?.length || 0})`}
          icon="clipboard-list"
        >
          <DataTable
            columns={fieldColumns}
            data={collection?.fields || []}
            keyField="name"
            emptyText="Нет полей"
          />
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}

export default ViewCollectionPage;
