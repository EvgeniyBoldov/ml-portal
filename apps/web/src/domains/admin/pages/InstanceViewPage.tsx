/**
 * InstanceViewPage v2 - View tool instance details
 *
 * Two tabs:
 * 1. General - name, group, url, config, health status
 * 2. Credentials - list of credentials for this instance
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, credentialsApi, type Credential } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  EntityPage,
  ContentBlock,
  Badge,
  DataTable,
  Button,
  ConfirmDialog,
  type BreadcrumbItem,
  type DataTableColumn,
} from '@/shared/ui';

export function InstanceViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [activeTab, setActiveTab] = useState('general');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: instance, isLoading } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !!id,
  });

  const { data: credentials = [], isLoading: credsLoading } = useQuery({
    queryKey: qk.credentials.list({ instance_id: id }),
    queryFn: () => credentialsApi.list({ instance_id: id! }),
    enabled: !!id,
  });

  const healthCheckMutation = useMutation({
    mutationFn: () => toolInstancesApi.healthCheck(id!),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.detail(id!) });
      showSuccess(`Health: ${result.status}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инстансы', href: '/admin/instances' },
    { label: instance?.name || 'Инстанс' },
  ];

  const credentialColumns: DataTableColumn<Credential>[] = [
    {
      key: 'auth_type',
      label: 'ТИП',
      width: 100,
      render: (c) => <Badge tone="neutral" size="small">{c.auth_type}</Badge>,
    },
    {
      key: 'owner',
      label: 'ВЛАДЕЛЕЦ',
      render: (c) => {
        if (c.owner_platform) return <Badge tone="info" size="small">Платформа</Badge>;
        if (c.owner_tenant_id) return <span style={{ fontSize: '0.8125rem' }}>Тенант: <code>{c.owner_tenant_id.slice(0, 8)}...</code></span>;
        if (c.owner_user_id) return <span style={{ fontSize: '0.8125rem' }}>Юзер: <code>{c.owner_user_id.slice(0, 8)}...</code></span>;
        return <span style={{ color: 'var(--text-secondary)' }}>—</span>;
      },
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      render: (c) => (
        <Badge tone={c.is_active ? 'success' : 'neutral'} size="small">
          {c.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      width: 120,
      render: (c) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
          {new Date(c.created_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
  ];

  const tabs = [
    { id: 'general', label: 'Общее' },
    { id: 'credentials', label: `Креды (${credentials.length})` },
  ];

  return (
    <EntityPage
      mode="view"
      entityName={instance?.name || 'Инстанс'}
      entityTypeLabel="инстанса"
      backPath="/admin/instances"
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      showDelete={false}
      onEdit={() => navigate(`/admin/instances/${id}/edit`)}
      actionButtons={[
        <Button key="edit" variant="primary" onClick={() => navigate(`/admin/instances/${id}/edit`)}>
          Редактировать
        </Button>,
      ]}
      tabsBar={
        <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border-color)' }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '0.75rem 1.25rem',
                background: 'none',
                border: 'none',
                borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
                color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontWeight: activeTab === tab.id ? 500 : 400,
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      }
      noPadding
    >
      {activeTab === 'general' && (
        <div style={{ padding: '1.5rem' }}>
          <ContentBlock
            title="Основные параметры"
            icon="server"
            headerActions={
              <Badge tone={instance?.is_active ? 'success' : 'neutral'} size="small">
                {instance?.is_active ? 'Активен' : 'Неактивен'}
              </Badge>
            }
            fields={[
              { key: 'name', label: 'Название', type: 'text', disabled: true },
              { key: 'group', label: 'Группа', type: 'text', disabled: true },
              { key: 'url', label: 'URL', type: 'text', disabled: true },
              { key: 'description', label: 'Описание', type: 'textarea', disabled: true, rows: 2 },
            ]}
            data={{
              name: instance?.name || '',
              group: instance?.tool_group_name || instance?.tool_group_slug || '—',
              url: instance?.url || '—',
              description: instance?.description || '',
            }}
          />

          {instance?.config && Object.keys(instance.config).length > 0 && (
            <ContentBlock title="Конфигурация" icon="settings" style={{ marginTop: '1rem' }}>
              <pre style={{
                background: 'var(--bg-secondary)',
                padding: '1rem',
                borderRadius: '8px',
                overflow: 'auto',
                fontSize: '0.875rem',
                margin: 0,
              }}>
                {JSON.stringify(instance.config, null, 2)}
              </pre>
            </ContentBlock>
          )}

          <ContentBlock title="Health Check" icon="activity" style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              {instance?.health_status ? (
                <Badge tone={instance.health_status === 'healthy' ? 'success' : 'warn'} size="small">
                  {instance.health_status}
                </Badge>
              ) : (
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Не проверялся</span>
              )}
              <Button
                variant="outline"
                size="small"
                onClick={() => healthCheckMutation.mutate()}
                disabled={healthCheckMutation.isPending}
              >
                {healthCheckMutation.isPending ? 'Проверка...' : 'Проверить'}
              </Button>
            </div>
          </ContentBlock>
        </div>
      )}

      {activeTab === 'credentials' && (
        <div style={{ padding: '1.5rem' }}>
          <ContentBlock title="Учётные данные" icon="key">
            <DataTable
              columns={credentialColumns}
              data={credentials}
              keyField="id"
              loading={credsLoading}
              emptyText="Нет учётных данных для этого инстанса"
            />
          </ContentBlock>
        </div>
      )}
    </EntityPage>
  );
}

export default InstanceViewPage;
