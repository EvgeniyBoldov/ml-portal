/**
 * ViewCollectionPage - View collection details with EntityPageV2 + Tab architecture
 * 
 * Declarative tabs with existing shared blocks inside.
 */
import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ContentBlock, Badge, DataTable, type DataTableColumn, type BreadcrumbItem } from '@/shared/ui';
import { collectionsApi } from '@shared/api/collections';
import { adminApi } from '@shared/api/admin';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';

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
    queryKey: qk.collections.detail(id!),
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

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Коллекции', href: '/admin/collections' },
    { label: collection?.name || 'Коллекция' },
  ];

  return (
    <EntityPageV2
      title={collection?.name || 'Коллекция'}
      mode="view"
      loading={isLoading}
      breadcrumbs={breadcrumbs}
      backPath="/admin/collections"
    >
      <Tab title="Основное" layout="grid" id="general">
        <ContentBlock
          title="Основная информация"
          icon="database"
          fields={[
            { key: 'slug', label: 'Slug', type: 'code' as const },
            { key: 'name', label: 'Название', type: 'text' as const },
            { key: 'tenant', label: 'Тенант', type: 'text' as const },
            { key: 'table_name', label: 'Таблица', type: 'code' as const },
            { key: 'row_count', label: 'Записей', type: 'text' as const },
            { key: 'created_at', label: 'Создана', type: 'text' as const },
            { key: 'description', label: 'Описание', type: 'text' as const },
          ]}
          data={{
            slug: collection?.slug || '—',
            name: collection?.name || '—',
            tenant: tenant ? tenant.name : (collection?.tenant_id || '—'),
            table_name: collection?.table_name || '—',
            row_count: collection?.row_count?.toLocaleString() || '0',
            created_at: collection?.created_at ? new Date(collection.created_at).toLocaleString('ru-RU') : '—',
            description: collection?.description || '—',
          }}
        />

        <ContentBlock title="Статус" icon="shield">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Статус</div>
              <Badge variant={collection?.is_active ? 'success' : 'default'}>
                {collection?.is_active ? 'Активна' : 'Неактивна'}
              </Badge>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Возможности</div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <Badge variant="info">SQL</Badge>
                {collection?.has_vector_search && <Badge variant="warning">VECTOR</Badge>}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>Обновлена</div>
              <span>{collection?.updated_at ? new Date(collection.updated_at).toLocaleString('ru-RU') : '—'}</span>
            </div>
          </div>
        </ContentBlock>
      </Tab>

      <Tab title="Поля" layout="full" id="fields">
        <div style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Поля коллекции ({collection?.fields?.length || 0})
          </h3>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Структура полей и их характеристики
          </p>
        </div>
        <DataTable
          columns={fieldColumns}
          data={collection?.fields || []}
          keyField="name"
          emptyText="Нет полей"
        />
      </Tab>
    </EntityPageV2>
  );
}

export default ViewCollectionPage;
