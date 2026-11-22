import { Link, useSearchParams } from 'react-router-dom';

import type { DiscoveredToolListItem } from '@/shared/api/discoveredTools';
import {
  Badge,
  DataTable,
  type DataTableColumn,
  type DataTableFilterValue,
} from '@/shared/ui';
import {
  BUILTIN_PROVIDER,
  TOOLS_PATH,
  deliveryLabels,
  matchesTool,
  providerKind,
  providerName,
  riskKey,
  riskOptions,
  sourceLabels,
  toolRisk,
  toolSourceLabels,
} from '@/domains/admin/shared/toolCatalog';
import styles from './ToolRegistryTable.module.css';

function ToolLink({ tool }: { tool: DiscoveredToolListItem }) {
  const [params] = useSearchParams();
  return (
    <Link
      to={{
        pathname: `${TOOLS_PATH}/discovered/${tool.id}`,
        search: params.toString(),
      }}
    >
      {tool.name}
    </Link>
  );
}

const sourceOptions = Object.entries(sourceLabels).map(([value, label]) => ({
  value,
  label,
}));
const deliveryOptions = Object.entries(deliveryLabels).map(
  ([value, label]) => ({ value, label })
);
deliveryOptions.push({ value: 'runtime', label: 'Управляет runtime' });

function deliveryLabel(tool: DiscoveredToolListItem) {
  return tool.runtime_managed
    ? 'Управляет runtime'
    : deliveryLabels[tool.result_delivery];
}

function buildColumns(
  providerOptions: { value: string; label: string }[]
): DataTableColumn<DiscoveredToolListItem>[] {
  return [
    {
      key: 'name',
      label: 'Инструмент',
      sortable: true,
      render: tool => (
        <div className={styles.cell}>
          <ToolLink tool={tool} />
          {tool.slug !== tool.name && <code>{tool.slug}</code>}
          {!tool.is_active && (
            <Badge size="small" tone="warn">
              Не обнаружен
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: 'provider',
      label: 'Провайдер',
      sortable: true,
      sortValue: providerName,
      filter: {
        kind: 'select',
        options: providerOptions,
        getValue: tool => tool.provider_instance_id ?? BUILTIN_PROVIDER,
      },
      render: tool => (
        <div className={styles.cell}>
          {tool.provider_instance_id ? (
            <Link to={`/admin/connectors/${tool.provider_instance_id}`}>
              {providerName(tool)}
            </Link>
          ) : (
            <strong>{providerName(tool)}</strong>
          )}
          <small>{providerKind(tool)}</small>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'Тип данных',
      sortable: true,
      sortValue: tool => toolSourceLabels(tool).join(', ') || null,
      filter: {
        kind: 'select',
        options: sourceOptions,
        getValue: tool => tool.source_types,
      },
      render: tool => toolSourceLabels(tool).join(', ') || '—',
    },
    {
      key: 'risk',
      label: 'Риск',
      sortable: true,
      sortValue: tool => toolRisk(tool).sortOrder,
      filter: { kind: 'select', options: riskOptions, getValue: riskKey },
      render: tool => {
        const { label, tone } = toolRisk(tool);
        return <Badge tone={tone}>{label}</Badge>;
      },
    },
    {
      key: 'delivery',
      label: 'Доставка ответа',
      sortable: true,
      sortValue: deliveryLabel,
      filter: {
        kind: 'select',
        options: deliveryOptions,
        getValue: tool =>
          tool.runtime_managed ? 'runtime' : tool.result_delivery,
      },
      render: tool => (
        <Badge tone={tool.result_delivery === 'store' ? 'info' : 'neutral'}>
          {deliveryLabel(tool)}
        </Badge>
      ),
    },
  ];
}

interface ToolRegistryTableProps {
  tools: DiscoveredToolListItem[];
  providerOptions: { value: string; label: string }[];
  columnFilters: Record<string, DataTableFilterValue>;
  onColumnFiltersChange: (
    filters: Record<string, DataTableFilterValue>
  ) => void;
  search: string;
  loading: boolean;
  paginated: boolean;
  page: number;
  onPageChange: (page: number) => void;
}

export function ToolRegistryTable({
  tools,
  providerOptions,
  columnFilters,
  onColumnFiltersChange,
  search,
  loading,
  paginated,
  page,
  onPageChange,
}: ToolRegistryTableProps) {
  const hasFilters = Object.values(columnFilters).some(Boolean);
  return (
    <>
      <p className={styles.scrollHint}>
        Прокрутите таблицу вправо, чтобы увидеть остальные колонки и фильтры.
      </p>
      <DataTable
        className={styles.table}
        columns={buildColumns(providerOptions)}
        data={tools}
        keyField="id"
        loading={loading}
        searchable
        searchControl="external"
        searchValue={search}
        searchFilter={matchesTool}
        columnFilters={columnFilters}
        onColumnFiltersChange={onColumnFiltersChange}
        emptyState={
          <p>
            {search.trim() || hasFilters
              ? 'Ничего не найдено'
              : 'Инструменты ещё не обнаружены'}
          </p>
        }
        paginated={paginated}
        currentPage={page}
        onPageChange={onPageChange}
        pageSize={25}
        pageSizeOptions={[25]}
      />
    </>
  );
}
