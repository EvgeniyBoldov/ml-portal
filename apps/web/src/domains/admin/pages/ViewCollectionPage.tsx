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

  const TYPE_TONES: Record<string, 'info' | 'success' | 'warn' | 'neutral'> = {
    string: 'info',
    text: 'info',
    integer: 'success',
    float: 'success',
    number: 'success',
    boolean: 'warn',
    date: 'neutral',
    datetime: 'neutral',
    vector: 'danger' as any,
    json: 'warn',
  };

  const fieldColumns: DataTableColumn<CollectionField>[] = [
    {
      key: 'name',
      label: 'Поле',
      render: (row) => <code style={{ fontSize: '0.875rem' }}>{row.name}</code>,
    },
    {
      key: 'type',
      label: 'Тип',
      width: 120,
      render: (row) => (
        <Badge tone={TYPE_TONES[row.type] || 'neutral'}>{row.type}</Badge>
      ),
    },
    {
      key: 'required',
      label: 'Обязательное',
      width: 120,
      render: (row) => (
        <Badge tone={row.required ? 'warn' : 'neutral'}>
          {row.required ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'search_modes',
      label: 'Режимы поиска',
      width: 180,
      render: (row) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {row.search_modes?.length ? row.search_modes.map(mode => (
            <Badge key={mode} tone={mode === 'vector' ? 'warn' : mode === 'fulltext' ? 'success' : 'info'}>
              {mode}
            </Badge>
          )) : <span style={{ color: 'var(--text-secondary)' }}>—</span>}
        </div>
      ),
    },
    {
      key: 'description',
      label: 'Описание',
      render: (row) => row.description || <span style={{ color: 'var(--text-secondary)' }}>—</span>,
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

        <ContentBlock
          title="Статус"
          icon="shield"
          fields={[
            { key: 'is_active', label: 'Статус', type: 'boolean' as const },
            {
              key: 'capabilities',
              label: 'Возможности',
              type: 'custom' as const,
              render: () => (
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <Badge tone="info">SQL</Badge>
                  {collection?.has_vector_search && <Badge tone="warn">VECTOR</Badge>}
                </div>
              ),
            },
            { key: 'updated_at', label: 'Обновлена', type: 'date' as const },
          ]}
          data={{
            is_active: collection?.is_active ?? false,
            capabilities: null,
            updated_at: collection?.updated_at || '—',
          }}
        />
      </Tab>

      <Tab title="Поля" layout="full" id="fields" badge={collection?.fields?.length || undefined}>
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
