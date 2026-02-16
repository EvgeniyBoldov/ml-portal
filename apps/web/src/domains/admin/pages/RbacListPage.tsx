import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { rbacApi, type EnrichedRule } from '@/shared/api/rbac';
import { Badge, DataTable, type DataTableColumn, EntityPageV2, Input } from '@/shared/ui';
import { Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import styles from './RbacListPage.module.css';

export function RbacListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: rules = [], isLoading } = useQuery({
    queryKey: qk.rbac.list({}),
    queryFn: () => rbacApi.listEnrichedRules({}),
  });

  const filtered = useMemo(() => {
    if (!search.trim()) {
      return rules;
    }

    const q = search.toLowerCase();
    return rules.filter((rule) => {
      const ownerName = rule.owner.name.toLowerCase();
      const resourceName = rule.resource.name.toLowerCase();
      return (
        ownerName.includes(q)
        || resourceName.includes(q)
        || rule.resource.type.toLowerCase().includes(q)
        || rule.effect.toLowerCase().includes(q)
      );
    });
  }, [rules, search]);

  const columns: DataTableColumn<EnrichedRule>[] = [
    {
      key: 'owner',
      label: 'Владелец',
      render: (row) => (
        <div className={styles['owner-cell']}>
          <span className={styles['owner-name']}>{row.owner.name}</span>
          <Badge tone="neutral">{row.owner.level}</Badge>
        </div>
      ),
    },
    {
      key: 'resource',
      label: 'Ресурс',
      render: (row) => `${row.resource.name} (${row.resource.type})`,
    },
    {
      key: 'effect',
      label: 'Эффект',
      render: (row) => (
        <Badge tone={row.effect === 'allow' ? 'success' : 'danger'}>
          {row.effect === 'allow' ? 'Разрешён' : 'Запрещён'}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'Создано',
      render: (row) =>
        new Date(row.created_at).toLocaleDateString('ru-RU', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
        }),
    },
  ];

  return (
    <EntityPageV2
      title="RBAC"
      mode="view"
      headerActions={(
        <Input
          placeholder="Поиск правил..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      )}
    >
      <Tab title="Правила" layout="full" badge={filtered.length}>
        <DataTable
          columns={columns}
          data={filtered}
          keyField="id"
          loading={isLoading}
          emptyText="RBAC правила не найдены"
          onRowClick={(row) => navigate(`/admin/rbac/${row.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default RbacListPage;
