/**
 * DiscoveredToolsPage — реестр обнаруженных инструментов (local + MCP)
 *
 * Заменяет старый registry list. Показывает все discovered tools
 * с возможностью фильтрации и запуска rescan.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { discoveredToolsApi, type DiscoveredToolListItem } from '@/shared/api/discoveredTools';
import { useNavigate } from 'react-router-dom';
import {
  EntityPageV2,
  Tab,
} from '@/shared/ui/EntityPage';
import {
  DataTable,
  type DataTableColumn,
  Badge,
  Button,
  Input,
} from '@/shared/ui';
import { formatDomainLabel, formatDomainTone } from '../shared/domainLabels';

export function DiscoveredToolsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');

  const { data: tools = [], isLoading } = useQuery({
    queryKey: qk.discoveredTools.list({}),
    queryFn: () => discoveredToolsApi.list({}),
    staleTime: 30_000,
  });

  const rescanMutation = useMutation({
    mutationFn: () => discoveredToolsApi.rescan(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.discoveredTools.all() });
    },
  });

  const filtered = search
    ? tools.filter(
        (t) =>
          t.slug.toLowerCase().includes(search.toLowerCase()) ||
          t.name.toLowerCase().includes(search.toLowerCase()) ||
          (t.description || '').toLowerCase().includes(search.toLowerCase()),
      )
    : tools;

  const columns: DataTableColumn<DiscoveredToolListItem>[] = [
    {
      key: 'slug',
      label: 'Slug / Имя',
      width: 280,
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Slug или имя',
        getValue: (row) => `${row.slug ?? ''} ${row.name ?? ''}`,
      },
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'source',
      label: 'Источник',
      width: 100,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все источники',
        options: [
          { value: 'local', label: 'Local' },
          { value: 'mcp', label: 'MCP' },
        ],
        getValue: (row) => row.source,
      },
      render: (row) => (
        <Badge tone={row.source === 'local' ? 'info' : 'warn'}>{row.source}</Badge>
      ),
    },
    {
      key: 'connector_slug',
      label: 'Коннектор',
      width: 180,
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Slug коннектора',
        getValue: (row) => row.connector_slug ?? '',
      },
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.connector_slug || '—'}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>{row.connector_name || '—'}</div>
        </div>
      ),
    },
    {
      key: 'domains',
      label: 'Домен',
      width: 200,
      filter: {
        kind: 'tags',
        placeholder: 'Домены',
        match: 'any',
        getValue: (row) => row.domains,
      },
      render: (row) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {row.domains.map((domain) => (
            <Badge key={domain} tone={formatDomainTone(domain)} size="small">
              {formatDomainLabel(domain)}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      key: 'is_active',
      label: 'Статус',
      width: 100,
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: [
          { value: 'true', label: 'Активен' },
          { value: 'false', label: 'Неактивен' },
        ],
        getValue: (row) => String(row.is_active),
      },
      render: (row) => (
        <Badge tone={row.is_active ? 'success' : 'neutral'}>
          {row.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'description',
      label: 'Описание',
      filter: {
        kind: 'text',
        placeholder: 'Описание',
        getValue: (row) => row.description ?? '',
      },
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
          {row.description ? (row.description.length > 80 ? row.description.slice(0, 80) + '…' : row.description) : '—'}
        </span>
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Инструменты"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск инструментов..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      }
      actionButtons={
        <Button
          onClick={() => rescanMutation.mutate()}
          disabled={rescanMutation.isPending}
        >
          {rescanMutation.isPending ? 'Сканирование...' : 'Rescan'}
        </Button>
      }
    >
      <Tab
        title="Все инструменты"
        layout="full"
        badge={tools.length}
      >
        <DataTable
          columns={columns}
          data={filtered}
          keyField="id"
          loading={isLoading}
          emptyText="Инструменты не обнаружены. Запустите Rescan."
          paginated
          pageSizeOptions={[10, 25, 50, 100]}
          onRowClick={(row) => navigate(`/admin/tools/discovered/${row.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default DiscoveredToolsPage;
