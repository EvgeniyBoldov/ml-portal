/**
 * RBACRulesTable - Universal self-contained RBAC rules component.
 *
 * Modes:
 * - mode="platform" → Platform rules. Edit effect only (rules auto-created).
 * - mode="tenant"   → Tenant rules. Create + edit + delete.
 * - mode="user"     → User rules. Create + edit + delete.
 * - mode="global"   → Read-only overview of all rules across all levels.
 *
 * The component fetches its own data and handles all mutations internally.
 * Pages just pass mode + ownerId.
 */
import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  rbacApi,
  type EnrichedRule,
  type EnrichedRulesFilters,
  type RbacEffect,
  type RbacRuleCreate,
} from '@/shared/api/rbac';
import { agentsApi, type Agent } from '@/shared/api/agents';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import Badge from '../Badge';
import Button from '../Button';
import { Select } from '../Select';
import styles from './RBACRulesTable.module.css';

export type RBACTableMode = 'platform' | 'tenant' | 'user' | 'global';

type SortField = 'resource' | 'effect' | 'level' | 'date' | 'owner';
type SortDir = 'asc' | 'desc';

interface RBACRulesTableProps {
  mode: RBACTableMode;
  /** Owner ID: user_id for mode="user", tenant_id for mode="tenant". Ignored for platform/global. */
  ownerId?: string;
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

export function RBACRulesTable({ mode, ownerId }: RBACRulesTableProps) {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [filterResourceType, setFilterResourceType] = useState<string>('');
  const [filterEffect, setFilterEffect] = useState<string>('');
  const [filterLevel, setFilterLevel] = useState<string>('');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [sortField, setSortField] = useState<SortField>('resource');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const isGlobal = mode === 'global';
  const canEdit = mode === 'tenant' || mode === 'user';
  const canCreateDelete = mode === 'tenant' || mode === 'user';

  // ─── Query ──────────────────────────────────────────────────────────

  const apiFilters: EnrichedRulesFilters = useMemo(() => {
    const f: EnrichedRulesFilters = {};
    if (mode === 'user' && ownerId) {
      f.owner_user_id = ownerId;
    } else if (mode === 'tenant' && ownerId) {
      f.owner_tenant_id = ownerId;
    } else if (mode === 'platform') {
      f.owner_platform = true;
    }
    return f;
  }, [mode, ownerId]);

  const queryKey = useMemo(
    () => [...qk.rbac.enrichedRules(apiFilters as Record<string, unknown>), mode],
    [apiFilters, mode],
  );

  const { data: rules = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => rbacApi.listEnrichedRules(apiFilters),
  });

  // Load agents and instances for resource names
  const { data: agents = [] } = useQuery({
    queryKey: qk.agents.list({}),
    queryFn: () => agentsApi.list({}),
  });

  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  // ─── Mutations ──────────────────────────────────────────────────────

  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: qk.rbac.all() }),
    [queryClient],
  );

  const toggleEffectMutation = useMutation({
    mutationFn: ({ ruleId, newEffect }: { ruleId: string; newEffect: RbacEffect }) =>
      rbacApi.updateRule(ruleId, { effect: newEffect }),
    onSuccess: invalidate,
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => rbacApi.deleteRule(ruleId),
    onSuccess: () => {
      setConfirmDeleteId(null);
      invalidate();
    },
  });

  const createRuleMutation = useMutation({
    mutationFn: (data: RbacRuleCreate) => rbacApi.createRule(data),
    onSuccess: invalidate,
  });

  // ─── Handlers ───────────────────────────────────────────────────────

  const handleToggleEffect = (rule: EnrichedRule) => {
    const newEffect: RbacEffect = rule.effect === 'allow' ? 'deny' : 'allow';
    toggleEffectMutation.mutate({ ruleId: rule.id, newEffect });
  };

  const handleDeleteConfirm = () => {
    if (confirmDeleteId) deleteRuleMutation.mutate(confirmDeleteId);
  };

  // ─── Resource name resolution ───────────────────────────────────────

  const getResourceName = useCallback((rule: EnrichedRule) => {
    // First check if backend already provided a name
    if (rule.resource.name && rule.resource.name !== rule.resource.id.slice(0, 8) + '...') {
      return rule.resource.name;
    }

    // Fallback: lookup in our cached data
    if (rule.resource.type === 'agent') {
      const agent = agents.find((a: Agent) => a.id === rule.resource.id);
      return agent ? agent.name : rule.resource.name;
    }
    
    if (rule.resource.type === 'instance') {
      const instance = instances.find((i: ToolInstance) => i.id === rule.resource.id);
      return instance ? instance.name : rule.resource.name;
    }

    return rule.resource.name;
  }, [agents, instances]);

  const getResourceDetails = useCallback((rule: EnrichedRule) => {
    if (rule.resource.type === 'instance') {
      const instance = instances.find((i: ToolInstance) => i.id === rule.resource.id);
      if (instance) {
        return {
          category: instance.category,
          url: instance.url,
        };
      }
    }
    
    return null;
  }, [instances]);

  // ─── Client-side filtering ─────────────────────────────────────────

  const filteredRules = useMemo(() => {
    let result = rules;

    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (r) =>
          getResourceName(r).toLowerCase().includes(q) ||
          r.owner.name.toLowerCase().includes(q),
      );
    }
    if (filterResourceType) {
      result = result.filter((r) => r.resource.type === filterResourceType);
    }
    if (filterEffect) {
      result = result.filter((r) => r.effect === filterEffect);
    }
    if (filterLevel) {
      result = result.filter((r) => r.owner.level === filterLevel);
    }

    return result;
  }, [rules, search, filterResourceType, filterEffect, filterLevel, getResourceName]);

  // ─── Client-side sorting ───────────────────────────────────────────

  const sortedRules = useMemo(() => {
    const sorted = [...filteredRules];
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'resource':
          cmp = getResourceName(a).localeCompare(getResourceName(b));
          break;
        case 'effect':
          cmp = a.effect.localeCompare(b.effect);
          break;
        case 'level':
          cmp = a.owner.level.localeCompare(b.owner.level);
          break;
        case 'date':
          cmp = a.created_at.localeCompare(b.created_at);
          break;
        case 'owner':
          cmp = a.owner.name.localeCompare(b.owner.name);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [filteredRules, sortField, sortDir, getResourceName]);

  // ─── Group by resource_type ────────────────────────────────────────

  const grouped = useMemo(() => {
    const groups: Record<string, EnrichedRule[]> = {};
    for (const rule of sortedRules) {
      const key = rule.resource.type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(rule);
    }
    const sortedEntries = Object.entries(groups).sort(
      ([a], [b]) => (RESOURCE_TYPE_ORDER[a] ?? 99) - (RESOURCE_TYPE_ORDER[b] ?? 99),
    );
    return sortedEntries;
  }, [sortedRules]);

  // ─── Sort helpers ──────────────────────────────────────────────────

  const toggleGroup = (key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

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

  // ─── Filter options ────────────────────────────────────────────────

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

  // ─── Determine grid class ─────────────────────────────────────────

  const gridClass = isGlobal
    ? styles.tableHeaderGlobal
    : mode === 'platform'
      ? styles.tableHeaderPlatform
      : canEdit
        ? styles.tableHeaderActions
        : '';
  const rowGridClass = isGlobal
    ? styles.rowGlobal
    : mode === 'platform'
      ? styles.rowPlatform
      : canEdit
        ? styles.rowActions
        : '';

  // ─── Render ────────────────────────────────────────────────────────

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
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
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
        <div className={`${styles.tableHeader} ${gridClass}`}>
          <div className={styles.sortable} onClick={() => handleSort('resource')}>
            Ресурс {renderSortIcon('resource')}
          </div>
          {isGlobal && (
            <div className={styles.sortable} onClick={() => handleSort('owner')}>
              Владелец {renderSortIcon('owner')}
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
          {canEdit && mode !== 'platform' && (
            <div>Действия</div>
          )}
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
                      className={`${styles.row} ${rowGridClass}`}
                    >
                      <div>
                        <div className={styles.resourceName}>{getResourceName(rule)}</div>
                        {(() => {
                          const details = getResourceDetails(rule);
                          if (details) {
                            return (
                              <div className={styles.resourceDetails}>
                                {details.category && (
                                  <span className={styles.resourceCategory}>
                                    {details.category}
                                  </span>
                                )}
                                {details.url && (
                                  <div className={styles.resourceUrl}>
                                    {details.url}
                                  </div>
                                )}
                              </div>
                            );
                          }
                          return null;
                        })()}
                      </div>
                      {isGlobal && (
                        <div className={styles.policyName}>{rule.owner.name}</div>
                      )}
                      <div>
                        {canEdit ? (
                          <button
                            className={styles.effectToggle}
                            onClick={() => handleToggleEffect(rule)}
                            disabled={toggleEffectMutation.isPending}
                            title="Нажмите для переключения"
                          >
                            <Badge tone={EFFECT_CONFIG[rule.effect]?.tone || 'neutral'}>
                              {EFFECT_CONFIG[rule.effect]?.label || rule.effect}
                            </Badge>
                          </button>
                        ) : (
                          <Badge tone={EFFECT_CONFIG[rule.effect]?.tone || 'neutral'}>
                            {EFFECT_CONFIG[rule.effect]?.label || rule.effect}
                          </Badge>
                        )}
                      </div>
                      <div>
                        <Badge tone="neutral" className={styles.levelBadge}>
                          {LEVEL_LABELS[rule.owner.level] || rule.owner.level}
                        </Badge>
                      </div>
                      <div className={styles.date}>
                        {new Date(rule.created_at).toLocaleDateString('ru')}
                      </div>
                      {canEdit && mode !== 'platform' && (
                        <div className={styles.actions}>
                          {canCreateDelete && (
                            confirmDeleteId === rule.id ? (
                              <div className={styles.confirmDelete}>
                                <Button
                                  variant="danger"
                                  size="sm"
                                  onClick={handleDeleteConfirm}
                                  disabled={deleteRuleMutation.isPending}
                                >
                                  Да
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => setConfirmDeleteId(null)}
                                >
                                  Нет
                                </Button>
                              </div>
                            ) : (
                              <button
                                className={styles.deleteBtn}
                                onClick={() => setConfirmDeleteId(rule.id)}
                                title="Удалить правило"
                              >
                                ✕
                              </button>
                            )
                          )}
                        </div>
                      )}
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
