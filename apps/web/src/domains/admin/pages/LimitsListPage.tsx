/**
 * LimitsListPage - Управление лимитами (EntityPageV2)
 * 
 * Execution constraints: max_steps, max_tool_calls, timeouts
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { limitsApi, type LimitListItem } from '@/shared/api/limits';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import { DataTable, type DataTableColumn, Badge, Button, Input } from '@/shared/ui';

export function LimitsListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');

  const { data: limits, isLoading, error } = useQuery({
    queryKey: qk.limits.list({}),
    queryFn: () => limitsApi.list({}),
  });

  const filteredLimits = useMemo(() => {
    if (!limits) return [];
    if (!q.trim()) return limits;
    const query = q.toLowerCase();
    return limits.filter((l) =>
      l.name.toLowerCase().includes(query) ||
      l.slug.toLowerCase().includes(query) ||
      l.description?.toLowerCase().includes(query)
    );
  }, [limits, q]);

  const handleRowClick = (limit: LimitListItem) => {
    navigate(`/admin/limits/${limit.slug}`);
  };

  const columns: DataTableColumn<LimitListItem>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      render: (limit) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{limit.name}</span>
          <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {limit.slug}
          </code>
        </div>
      ),
    },
    {
      key: 'versions_count',
      label: 'ВЕРСИИ',
      width: 80,
      render: (limit) => limit.versions_count,
    },
    {
      key: 'active_version',
      label: 'АКТИВНАЯ',
      width: 100,
      render: (limit) => limit.active_version
        ? <Badge tone="success" size="small">v{limit.active_version}</Badge>
        : <span style={{ color: 'var(--text-muted)' }}>—</span>,
    },
    {
      key: 'updated_at',
      label: 'ОБНОВЛЕНО',
      width: 140,
      render: (limit) => new Date(limit.updated_at).toLocaleDateString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
      }),
    },
  ];

  return (
    <EntityPageV2
      title="Лимиты"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск лимитов..."
          value={q}
          onChange={setQ}
        />
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/limits/new')}>
          Создать
        </Button>
      }
    >
      <Tab 
        title="Лимиты" 
        layout="full"
      >
        {error && (
          <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
            Не удалось загрузить лимиты. Попробуйте снова.
          </div>
        )}

        <DataTable
          columns={columns}
          data={filteredLimits}
          keyField="slug"
          loading={isLoading}
          emptyText="Лимиты не найдены. Нажмите «Создать» для добавления."
          paginated
          pageSize={20}
          onRowClick={handleRowClick}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default LimitsListPage;
