import { useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import type { EnrichedRule } from '@/shared/api/rbac';
import { Button, DataTable, Input, type DataTableColumn } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { AccessCheck } from '../components/access/AccessCheck';
import {
  AccessDecisionBadge,
  AccessStatusBadge,
} from '../components/access/AccessRuleBadges';
import { AccessRuleForm } from '../components/access/AccessRuleForm';
import {
  ACCESS_PATH,
  loadAccessRules,
  ownerName,
  ownerOptions,
  resourceTypeName,
  statusName,
} from '../components/access/accessRules';
import { RBAC_LEVEL_LABELS } from '../shared/rbacLabels';
import styles from './AccessRulesPage.module.css';

function ResourceLink({ rule }: { rule: EnrichedRule }) {
  const { search } = useLocation();
  return (
    <Link to={`${ACCESS_PATH}/${rule.id}`} state={{ search }}>
      {rule.resource.name}
    </Link>
  );
}

const columns: DataTableColumn<EnrichedRule>[] = [
  {
    key: 'resource',
    label: 'Ресурс',
    sortable: true,
    sortValue: row => row.resource.name,
    filter: {
      kind: 'select',
      placeholder: 'Тип ресурса',
      options: ['agent', 'instance', 'collection', 'tool', 'operation'].map(
        value => ({
          value,
          label: resourceTypeName(value),
        })
      ),
      getValue: row => row.resource.type,
    },
    render: row => (
      <div className={styles.cell}>
        <ResourceLink rule={row} />
        <span>{resourceTypeName(row.resource.type)}</span>
      </div>
    ),
  },
  {
    key: 'owner',
    label: 'Для кого',
    sortable: true,
    sortValue: row => ownerName(row.owner),
    filter: {
      kind: 'select',
      placeholder: 'Уровень',
      options: ownerOptions,
      getValue: row => row.owner.level,
    },
    render: row => (
      <div className={styles.cell}>
        <strong>{ownerName(row.owner)}</strong>
        {!row.owner.platform && (
          <span>{RBAC_LEVEL_LABELS[row.owner.level]}</span>
        )}
      </div>
    ),
  },
  {
    key: 'effect',
    label: 'Решение правила',
    sortable: true,
    sortValue: row => row.effect,
    filter: {
      kind: 'select',
      placeholder: 'Решение',
      options: [
        { value: 'allow', label: 'Разрешён' },
        { value: 'deny', label: 'Запрещён' },
      ],
    },
    render: row => <AccessDecisionBadge effect={row.effect} />,
  },
  {
    key: 'status',
    label: 'Статус',
    filter: {
      kind: 'select',
      placeholder: 'Статус',
      options: [
        { value: 'Действует', label: 'Действует' },
        { value: 'К удалению', label: 'К удалению' },
      ],
      getValue: statusName,
    },
    render: row => <AccessStatusBadge rule={row} />,
  },
];

function matchesRule(row: EnrichedRule, value: string) {
  const text = [
    row.resource.name,
    row.resource.slug,
    resourceTypeName(row.resource.type),
    ownerName(row.owner),
    RBAC_LEVEL_LABELS[row.owner.level],
    row.effect === 'allow' ? 'Разрешён' : 'Запрещён',
    statusName(row),
  ]
    .join(' ')
    .toLowerCase()
    .replace(/ё/g, 'е');
  return value
    .trim()
    .toLowerCase()
    .replace(/ё/g, 'е')
    .split(/\s+/)
    .every(word => text.includes(word));
}

export function AccessRulesPage() {
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(1);
  const rules = useQuery({
    queryKey: qk.rbac.accessRegister(),
    queryFn: loadAccessRules,
  });
  const items = rules.data ?? [];
  const search = params.get('q') ?? '';

  return (
    <>
      <EntityPageV2
        title="Права доступа"
        mode="view"
        breadcrumbs={[{ label: 'Права доступа' }]}
        defaultTab={params.get('tab') === 'check' ? 'check' : 'rules'}
        onTabChange={tab => {
          setParams(
            previous => {
              if (tab === 'check') previous.set('tab', 'check');
              else previous.delete('tab');
              return previous;
            },
            { replace: true }
          );
        }}
      >
        <Tab
          id="rules"
          title="Правила"
          badge={rules.data?.length}
          layout="full"
          actions={[
            <div className={styles.headerControls} key="rule-controls">
              <Input
                className={styles.search}
                type="search"
                aria-label="Поиск правил"
                placeholder="Ресурс, имя или решение"
                value={search}
                onChange={event => {
                  const value = event.target.value;
                  setPage(1);
                  setParams(
                    previous => {
                      if (value) previous.set('q', value);
                      else previous.delete('q');
                      return previous;
                    },
                    { replace: true }
                  );
                }}
              />
              <Button onClick={() => setCreating(true)}>Создать правило</Button>
            </div>,
          ]}
        >
          {rules.isError ? (
            <p role="alert">
              Не удалось загрузить правила.{' '}
              <Button variant="ghost" onClick={() => void rules.refetch()}>
                Повторить
              </Button>
            </p>
          ) : (
            <div className={styles.table}>
              <p className={styles.scrollHint}>
                Прокрутите таблицу вправо, чтобы увидеть решение и статус.
              </p>
              <DataTable
                columns={columns}
                data={items}
                searchable
                searchControl="external"
                searchValue={search}
                searchFilter={matchesRule}
                loading={rules.isPending}
                keyField="id"
                paginated={items.length > 25}
                currentPage={page}
                onPageChange={setPage}
                onColumnFiltersChange={() => setPage(1)}
                pageSize={25}
                pageSizeOptions={[25]}
                emptyText={
                  items.length
                    ? 'По выбранным условиям правил нет'
                    : 'Правил доступа ещё нет'
                }
              />
            </div>
          )}
        </Tab>
        <Tab id="check" title="Проверить доступ" layout="single">
          <AccessCheck />
        </Tab>
      </EntityPageV2>
      {creating && <AccessRuleForm onClose={() => setCreating(false)} />}
    </>
  );
}
