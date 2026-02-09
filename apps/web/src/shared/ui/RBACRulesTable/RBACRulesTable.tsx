/**
 * RBACRulesTable - Universal RBAC rules table with hierarchy, filters, sorting.
 *
 * Usage contexts:
 * - mode="user"   → User page tab, filters by level_id=userId
 * - mode="tenant" → Tenant page tab, filters by level_id=tenantId
 * - mode="global" → Global RBAC page, shows all rules with policy/context columns
 */
import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rbacApi, type EnrichedRule, type EnrichedRulesFilters, type ResourceType, type RbacEffect } from '@/shared/api/rbac';
import { qk } from '@/shared/api/keys';
import Badge from '../Badge';
import { Select } from '../Select';
import styles from './RBACRulesTable.module.css';

export type RBACTableMode = 'user' | 'tenant' | 'global';

type SortField = 'resource' | 'effect' | 'level' | 'date' | 'policy';
type SortDir = 'asc' | 'desc';

interface RBACRulesTableProps {
  mode: RBACTableMode;
  levelId?: string;
  rbacPolicyId?: string;
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  agent: 'Агенты',
  toolgroup: 'Группы инструментов',
  tool: 'Инструменты',
  instance: 'Инстансы',
};

const RESOURCE_TYPE_ICONS: Record<string, string> = {
  agent: '🤖',
  toolgroup: '🛠️',
  tool: '🔧',
  instance: '🖥️',
};

const RESOURCE_TYPE_ORDER: Record<string, number> = {
  agent: 0,
  toolgroup: 1,
  tool: 2,
  instance: 3,
};

const LEVEL_LABELS: Record<string, string> = {
  platform: 'Платформа',
  tenant: 'Тенант',
  user: 'Пользователь',
};

const EFFECT_CONFIG: Record<string, { label: string; tone: 'success' | 'danger' }> = {
  allow: { label: 'Разрешён', tone: 'success' },
  deny: { label: 'Запрещён', tone: 'danger' },
};

export function RBACRulesTable({ mode, levelId, rbacPolicyId }: RBACRulesTableProps) {
  const [search, setSearch] = useState('');
  const [filterResourceType, setFilterResourceType] = useState<string>('');
  const [filterEffect, setFilterEffect] = useState<string>('');
  const [filterLevel, setFilterLevel] = useState<string>('');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [sortField, setSortField] = useState<SortField>('resource');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const isGlobal = mode === 'global';

  // Build API filters based on mode
  const apiFilters: EnrichedRulesFilters = useMemo(() => {
    const f: EnrichedRulesFilters = {};
    if (rbacPolicyId) f.rbac_policy_id = rbacPolicyId;
    if (mode === 'user' && levelId) {
      f.level = 'user';
      f.level_id = levelId;
    } else if (mode === 'tenant' && levelId) {
      f.level = 'tenant';
      f.level_id = levelId;
    }
    return f;
  }, [mode, levelId, rbacPolicyId]);

  const { data: rules = [], isLoading } = useQuery({
    queryKey: qk.rbac.enrichedRules(apiFilters as Record<string, unknown>),
    queryFn: () => rbacApi.listEnrichedRules(apiFilters),
  });

  // Client-side filtering
  const filteredRules = useMemo(() => {
    let result = rules;

    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (r) =>
          r.resource.name.toLowerCase().includes(q) ||
          r.policy.name.toLowerCase().includes(q) ||
          (r.rule.context_name && r.rule.context_name.toLowerCase().includes(q))
      );
    }
    if (filterResourceType) {
      result = result.filter((r) => r.resource.type === filterResourceType);
    }
    if (filterEffect) {
      result = result.filter((r) => r.rule.effect === filterEffect);
    }
    if (filterLevel) {
      result = result.filter((r) => r.rule.level === filterLevel);
    }

    return result;
  }, [rules, search, filterResourceType, filterEffect, filterLevel]);

  // Client-side sorting
  const sortedRules = useMemo(() => {
    const sorted = [...filteredRules];
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'resource':
          cmp = a.resource.name.localeCompare(b.resource.name);
          break;
        case 'effect':
          cmp = a.rule.effect.localeCompare(b.rule.effect);
          break;
        case 'level':
          cmp = a.rule.level.localeCompare(b.rule.level);
          break;
        case 'date':
          cmp = a.rule.created_at.localeCompare(b.rule.created_at);
          break;
        case 'policy':
          cmp = a.policy.name.localeCompare(b.policy.name);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [filteredRules, sortField, sortDir]);

  // Group by resource_type
  const grouped = useMemo(() => {
    const groups: Record<string, EnrichedRule[]> = {};
    for (const rule of sortedRules) {
      const key = rule.resource.type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(rule);
    }
    // Sort groups by fixed order
    const sortedEntries = Object.entries(groups).sort(
      ([a], [b]) => (RESOURCE_TYPE_ORDER[a] ?? 99) - (RESOURCE_TYPE_ORDER[b] ?? 99)
    );
    return sortedEntries;
  }, [sortedRules]);

  // Toggle group collapse
  const toggleGroup = (key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Toggle sort
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const renderSortIcon = (field: SortField) => {
    if (sortField !== field) return <span className={styles.sortIcon}>↕</span>;
    return (
      <span className={`${styles.sortIcon} ${styles.sortIconActive}`}>
        {sortDir === 'asc' ? '↑' : '↓'}
      </span>
    );
  };

  // Filter options
  const resourceTypeOptions = [
    { value: '', label: 'Все типы' },
    { value: 'agent', label: 'Агенты' },
    { value: 'toolgroup', label: 'Группы' },
    { value: 'tool', label: 'Инструменты' },
    { value: 'instance', label: 'Инстансы' },
  ];

  const effectOptions = [
    { value: '', label: 'Все эффекты' },
    { value: 'allow', label: 'Разрешён' },
    { value: 'deny', label: 'Запрещён' },
  ];

  const levelOptions = [
    { value: '', label: 'Все уровни' },
    { value: 'platform', label: 'Платформа' },
    { value: 'tenant', label: 'Тенант' },
    { value: 'user', label: 'Пользователь' },
  ];

  if (isLoading) {
    return <div className={styles.empty}>Загрузка правил...</div>;
  }

  return (
    <div className={styles.container}>
      {/* Filters */}
      <div className={styles.filters}>
        <input
          type="text"
          placeholder="Поиск по ресурсу..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className={styles.searchInput}
        />
        <div className={styles.filterSelect}>
          <Select
            value={filterResourceType}
            onChange={setFilterResourceType}
            options={resourceTypeOptions}
            placeholder="Тип ресурса"
          />
        </div>
        <div className={styles.filterSelect}>
          <Select
            value={filterEffect}
            onChange={setFilterEffect}
            options={effectOptions}
            placeholder="Эффект"
          />
        </div>
        {isGlobal && (
          <div className={styles.filterSelect}>
            <Select
              value={filterLevel}
              onChange={setFilterLevel}
              options={levelOptions}
              placeholder="Уровень"
            />
          </div>
        )}
      </div>

      {/* Table */}
      <div className={styles.table}>
        {/* Header */}
        <div className={`${styles.tableHeader} ${isGlobal ? styles.tableHeaderGlobal : ''}`}>
          <div className={styles.sortable} onClick={() => handleSort('resource')}>
            Ресурс {renderSortIcon('resource')}
          </div>
          {isGlobal && (
            <div className={styles.sortable} onClick={() => handleSort('policy')}>
              Политика {renderSortIcon('policy')}
            </div>
          )}
          <div className={styles.sortable} onClick={() => handleSort('effect')}>
            Эффект {renderSortIcon('effect')}
          </div>
          <div className={styles.sortable} onClick={() => handleSort('level')}>
            Уровень {renderSortIcon('level')}
          </div>
          <div className={styles.sortable} onClick={() => handleSort('date')}>
            Создано {renderSortIcon('date')}
          </div>
        </div>

        {/* Body */}
        <div className={styles.tableBody}>
          {grouped.length === 0 ? (
            <div className={styles.empty}>
              {rules.length === 0
                ? 'Нет правил RBAC'
                : 'Нет правил, соответствующих фильтрам'}
            </div>
          ) : (
            grouped.map(([resourceType, groupRules]) => (
              <div key={resourceType} className={styles.group}>
                {/* Group header */}
                <div
                  className={styles.groupHeader}
                  onClick={() => toggleGroup(resourceType)}
                >
                  <span className={styles.groupIcon}>
                    {RESOURCE_TYPE_ICONS[resourceType] || '📦'}
                  </span>
                  {RESOURCE_TYPE_LABELS[resourceType] || resourceType}
                  <span className={styles.groupCount}>({groupRules.length})</span>
                  <span
                    className={`${styles.groupChevron} ${
                      !collapsedGroups.has(resourceType) ? styles.groupChevronOpen : ''
                    }`}
                  >
                    ▶
                  </span>
                </div>

                {/* Group rows */}
                {!collapsedGroups.has(resourceType) &&
                  groupRules.map((rule) => (
                    <div
                      key={rule.id}
                      className={`${styles.row} ${isGlobal ? styles.rowGlobal : ''}`}
                    >
                      <div>
                        <div className={styles.resourceName}>{rule.resource.name}</div>
                        <div className={styles.resourceId}>{rule.resource.id.slice(0, 8)}...</div>
                      </div>
                      {isGlobal && (
                        <div className={styles.policyName}>{rule.policy.name}</div>
                      )}
                      <div>
                        <Badge tone={EFFECT_CONFIG[rule.rule.effect]?.tone || 'neutral'}>
                          {EFFECT_CONFIG[rule.rule.effect]?.label || rule.rule.effect}
                        </Badge>
                      </div>
                      <div>
                        <Badge tone="neutral" className={styles.levelBadge}>
                          {LEVEL_LABELS[rule.rule.level] || rule.rule.level}
                        </Badge>
                        {rule.rule.context_name && (
                          <div className={styles.contextName}>{rule.rule.context_name}</div>
                        )}
                      </div>
                      <div className={styles.date}>
                        {new Date(rule.rule.created_at).toLocaleDateString('ru')}
                      </div>
                    </div>
                  ))}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Summary */}
      <div className={styles.summary}>
        <span>
          {filteredRules.length} из {rules.length} правил
        </span>
        <div className={styles.legend}>
          <span className={styles.legendItem}>
            <Badge tone="success">Разрешён</Badge>
          </span>
          <span className={styles.legendItem}>
            <Badge tone="danger">Запрещён</Badge>
          </span>
        </div>
      </div>
    </div>
  );
}

export default RBACRulesTable;
