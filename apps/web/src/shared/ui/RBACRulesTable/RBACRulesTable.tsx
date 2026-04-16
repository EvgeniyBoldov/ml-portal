/**
 * RBACRulesTable - shared RBAC table for scoped admin tabs.
 *
 * Uses the same DataTable pattern as the global RBAC list, but can hide
 * the owner column for tenant/user/platform scoped views.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DataTable, type DataTableColumn } from '@/shared/ui';
import { qk } from '@/shared/api/keys';
import { agentsApi, type Agent } from '@/shared/api/agents';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { rbacApi, type EnrichedRule, type EnrichedRulesFilters } from '@/shared/api/rbac';
import { buildRbacRuleColumns, resolveRbacSearchText } from '@/domains/admin/shared/rbacRuleTable';

export type RBACTableMode = 'platform' | 'tenant' | 'user' | 'global';

interface RBACRulesTableProps {
  mode: RBACTableMode;
  ownerId?: string;
  showOwner?: boolean;
  searchPlaceholder?: string;
}

export function RBACRulesTable({
  mode,
  ownerId,
  showOwner = false,
  searchPlaceholder = 'Поиск по владельцу, ресурсу или уровню...',
}: RBACRulesTableProps) {
  const [search, setSearch] = useState('');

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

  const { data: rules = [], isLoading } = useQuery({
    queryKey: [...qk.rbac.enrichedRules(apiFilters as Record<string, unknown>), mode],
    queryFn: () => rbacApi.listEnrichedRules(apiFilters),
  });

  const { data: agents = [] } = useQuery({
    queryKey: qk.agents.list({}),
    queryFn: () => agentsApi.list({}),
  });

  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  const agentById = useMemo(
    () => new Map<string, Agent>(agents.map((agent) => [agent.id, agent])),
    [agents],
  );

  const instanceById = useMemo(
    () => new Map<string, ToolInstance>(instances.map((instance) => [instance.id, instance])),
    [instances],
  );

  const filteredRules = useMemo(() => {
    if (!search.trim()) return rules;
    const q = search.toLowerCase();
    return rules.filter((row) => resolveRbacSearchText(row, agentById, instanceById).includes(q));
  }, [rules, search, agentById, instanceById]);

  const columns: DataTableColumn<EnrichedRule>[] = useMemo(
    () => buildRbacRuleColumns({ showOwner, agentById, instanceById }),
    [showOwner, agentById, instanceById],
  );

  return (
    <DataTable
      columns={columns}
      data={filteredRules}
      keyField="id"
      loading={isLoading}
      emptyText="RBAC правила не найдены"
      searchable
      searchPlaceholder={searchPlaceholder}
      searchValue={search}
      onSearchChange={setSearch}
      paginated
      pageSize={20}
    />
  );
}

export default RBACRulesTable;
