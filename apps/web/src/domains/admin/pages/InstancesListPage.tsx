/**
 * InstancesListPage - Управление коннекторами (v3)
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolInstancesApi, type ToolInstance } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Badge, Button, Input } from '@/shared/ui';

const CONNECTOR_LABELS: Record<string, { label: string; tone: 'info' | 'neutral' }> = {
  data: { label: 'Data', tone: 'info' },
  mcp: { label: 'MCP', tone: 'neutral' },
  model: { label: 'Model', tone: 'neutral' },
};

const SUBTYPE_OPTIONS = [
  { value: 'sql', label: 'SQL' },
  { value: 'api', label: 'API' },
];

const HEALTH_OPTIONS = [
  { value: 'healthy', label: 'healthy' },
  { value: 'unhealthy', label: 'unhealthy' },
  { value: 'unknown', label: 'unknown' },
];

function isSystemInstance(inst: ToolInstance): boolean {
  const providerKind = typeof inst.provider_kind === 'string'
    ? inst.provider_kind.toLowerCase()
    : typeof inst.config?.provider_kind === 'string'
      ? String(inst.config.provider_kind).toLowerCase()
      : '';
  return providerKind === 'local_documents' || providerKind === 'local_tables';
}

export function InstancesListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');

  const { data: instances, isLoading, error } = useQuery({
    queryKey: qk.toolInstances.list({ placement: 'remote' }),
    queryFn: () => toolInstancesApi.list({ placement: 'remote' }),
  });

  const filteredInstances = useMemo(() => {
    if (!instances) return [];
    if (!q.trim()) return instances;
    const query = q.toLowerCase();
    return instances.filter((inst: ToolInstance) =>
      inst.name?.toLowerCase().includes(query) ||
      inst.slug?.toLowerCase().includes(query) ||
      inst.connector_type?.toLowerCase().includes(query) ||
      inst.connector_subtype?.toLowerCase().includes(query) ||
      inst.health_status?.toLowerCase().includes(query)
    );
  }, [instances, q]);

  const columns: DataTableColumn<ToolInstance>[] = [
    {
      key: 'name',
      label: 'Название',
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Название или slug',
        getValue: (inst) => `${inst.name ?? ''} ${inst.slug ?? ''}`,
      },
      render: (inst) => (
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}>
          <span>{inst.name}</span>
          {isSystemInstance(inst) && <Badge tone="warn">system</Badge>}
        </span>
      ),
    },
    {
      key: 'connector_type',
      label: 'Тип',
      width: 100,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все типы',
        options: [
          { value: 'data', label: 'Data' },
          { value: 'mcp', label: 'MCP' },
          { value: 'model', label: 'Model' },
        ],
        getValue: (inst) => inst.connector_type,
      },
      render: (inst) => {
        const cfg = CONNECTOR_LABELS[inst.connector_type] ?? { label: inst.connector_type, tone: 'neutral' as const };
        return <Badge tone={cfg.tone}>{cfg.label}</Badge>;
      },
    },
    {
      key: 'connector_subtype',
      label: 'Подтип',
      width: 150,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все подтипы',
        options: SUBTYPE_OPTIONS,
        getValue: (inst) => inst.connector_subtype ?? '',
      },
      render: (inst) => (
        <Badge tone="neutral" size="small">
          {inst.connector_subtype || '—'}
        </Badge>
      ),
    },
    {
      key: 'is_active',
      label: 'Активен',
      width: 90,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: [
          { value: 'true', label: 'Да' },
          { value: 'false', label: 'Нет' },
        ],
        getValue: (inst) => String(inst.is_active),
      },
      render: (inst) => (
        <Badge tone={inst.is_active ? 'success' : 'neutral'}>
          {inst.is_active ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'health_status',
      label: 'Здоровье',
      width: 100,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: HEALTH_OPTIONS,
        getValue: (inst) => inst.health_status ?? '',
      },
      render: (inst) => {
        if (!inst.health_status) {
          return <span style={{ color: 'var(--text-secondary)' }}>—</span>;
        }
        let tone: 'success' | 'warn' | 'danger' | 'neutral' = 'neutral';
        if (inst.health_status === 'healthy') tone = 'success';
        else if (inst.health_status === 'unhealthy') tone = 'danger';
        else if (inst.health_status === 'unknown') tone = 'warn';
        return <Badge tone={tone}>{inst.health_status}</Badge>;
      },
    },
    {
      key: 'created_at',
      label: 'Создан',
      width: 150,
      sortable: true,
      filter: {
        kind: 'date-range',
        fromPlaceholder: 'От',
        toPlaceholder: 'До',
        getValue: (inst) => inst.created_at,
      },
      render: (inst) => {
        const d = new Date(inst.created_at);
        return (
          <span style={{ color: 'var(--text-secondary)' }}>
            {d.toLocaleDateString('ru-RU')} {d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
          </span>
        );
      },
    },
  ];

 return (
    <EntityPageV2
      title="Коннекторы"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск коннекторов..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/connectors/new')}>Создать коннектор</Button>
      }
    >
      <Tab title="Коннекторы" layout="full">
        {error && (
          <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
            Не удалось загрузить коннекторы. Попробуйте снова.
          </div>
        )}
        <DataTable
          columns={columns}
          data={filteredInstances}
          keyField="id"
          loading={isLoading}
          emptyText="Коннекторы не найдены. Нажмите «Создать коннектор» для добавления."
          paginated
          pageSize={20}
          onRowClick={(inst: ToolInstance) => navigate(`/admin/connectors/${inst.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default InstancesListPage;
