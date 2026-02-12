/**
 * CredentialsListPage - List of platform credentials
 * 
 * Shows all platform-level credentials with search and actions.
 * Follows the same pattern as LimitsListPage.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { credentialsApi, type Credential } from '@/shared/api/credentials';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import { AdminPage, DataTable, type DataTableColumn, Badge } from '@/shared/ui';

export function CredentialsListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');

  const { data: credentials, isLoading, error } = useQuery({
    queryKey: qk.credentials.list({ owner_platform: true }),
    queryFn: () => credentialsApi.list({ owner_platform: true }),
  });

  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list(),
    queryFn: () => toolInstancesApi.list(),
  });

  const instanceMap = useMemo(() => {
    const map = new Map<string, ToolInstance>();
    instances.forEach((i: ToolInstance) => map.set(i.id, i));
    return map;
  }, [instances]);

  const filteredCredentials = useMemo(() => {
    if (!credentials) return [];
    if (!q.trim()) return credentials;
    const query = q.toLowerCase();
    return credentials.filter((c) => {
      const inst = instanceMap.get(c.instance_id);
      return (
        inst?.name.toLowerCase().includes(query) ||
        c.instance_id.toLowerCase().includes(query) ||
        c.auth_type.toLowerCase().includes(query)
      );
    });
  }, [credentials, q, instanceMap]);

  const handleRowClick = (credential: Credential) => {
    navigate(`/admin/credentials/${credential.id}`);
  };

  const AUTH_TYPE_LABELS: Record<string, string> = {
    token: 'Bearer Token',
    basic: 'Basic Auth',
    api_key: 'API Key',
    oauth: 'OAuth 2.0',
  };

  const columns: DataTableColumn<Credential>[] = [
    {
      key: 'instance_id',
      label: 'ИНСТАНС',
      render: (c) => {
        const inst = instanceMap.get(c.instance_id);
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontWeight: 500 }}>
              {inst?.name || c.instance_id.slice(0, 8) + '...'}
            </span>
            <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {c.instance_id.slice(0, 8)}...
            </code>
          </div>
        );
      },
    },
    {
      key: 'auth_type',
      label: 'ТИП АВТОРИЗАЦИИ',
      width: 140,
      render: (c) => AUTH_TYPE_LABELS[c.auth_type] || c.auth_type,
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      render: (c) => (
        <Badge tone={c.is_active ? 'success' : 'neutral'} size="small">
          {c.is_active ? 'Активен' : 'Отключен'}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      width: 140,
      render: (c) => new Date(c.created_at).toLocaleDateString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
      }),
    },
  ];

  return (
    <AdminPage
      title="Общие доступы"
      subtitle="Управление учетными данными для внешних сервисов и API"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск доступов..."
      actions={[
        {
          label: 'Создать',
          onClick: () => navigate('/admin/credentials/new'),
          variant: 'primary',
        },
      ]}
    >
      {error && (
        <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
          Не удалось загрузить доступы. Попробуйте снова.
        </div>
      )}

      <DataTable
        columns={columns}
        data={filteredCredentials || []}
        keyField="id"
        loading={isLoading}
        emptyText="Доступы не найдены. Нажмите «Создать» для добавления."
        onRowClick={handleRowClick}
      />
    </AdminPage>
  );
}

export default CredentialsListPage;
