/**
 * RbacListPage — global RBAC management surface.
 *
 * Uses the shared DataTable pattern:
 * - sortable columns
 * - header filters
 * - page-level search in the EntityPage header
 * - row navigation to effective rule view
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { Button, DataTable, FormModal, Input, Select } from '@/shared/ui';
import { qk } from '@/shared/api/keys';
import { adminApi } from '@/shared/api/admin';
import { agentsApi, type Agent } from '@/shared/api/agents';
import { discoveredToolsApi } from '@/shared/api/discoveredTools';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { tenantApi } from '@/shared/api/tenant';
import { rbacApi, type EnrichedRule, type RbacEffect, type RbacRuleCreate, type ResourceType } from '@/shared/api/rbac';
import { buildRbacRuleColumns, resolveRbacSearchText } from '../shared/rbacRuleTable';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

const EFFECT_OPTIONS = [
  { value: 'allow', label: 'Разрешён' },
  { value: 'deny', label: 'Запрещён' },
];

export function RbacListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [draftLevel, setDraftLevel] = useState<'platform' | 'tenant' | 'user'>('tenant');
  const [draftOwnerId, setDraftOwnerId] = useState('');
  const [draftResourceType, setDraftResourceType] = useState<ResourceType>('agent');
  const [draftResourceId, setDraftResourceId] = useState('');
  const [draftEffect, setDraftEffect] = useState<RbacEffect>('deny');

  const { data: rules = [], isLoading, error } = useQuery({
    queryKey: qk.rbac.enrichedRules({}),
    queryFn: () => rbacApi.listEnrichedRules(),
    staleTime: 30_000,
  });

  const { data: agents = [] } = useQuery({
    queryKey: qk.agents.list({}),
    queryFn: () => agentsApi.list({}),
  });

  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({ placement: 'remote' }),
    queryFn: () => toolInstancesApi.list({ placement: 'remote' }),
  });

  const { data: usersData } = useQuery({
    queryKey: qk.admin.users.list({ limit: 100 }),
    queryFn: () => adminApi.getUsers({ limit: 100 }),
    enabled: isComposerOpen,
    staleTime: 60_000,
  });

  const { data: tenantsData } = useQuery({
    queryKey: qk.admin.tenants.list(),
    queryFn: () => tenantApi.getTenants({ size: 100 }),
    enabled: isComposerOpen,
    staleTime: 60_000,
  });

  const { data: localTools = [] } = useQuery({
    queryKey: qk.discoveredTools.list({ source: 'local', is_active: true }),
    queryFn: () => discoveredToolsApi.list({ source: 'local', is_active: true }),
    enabled: isComposerOpen,
    staleTime: 60_000,
  });

  const { data: localDataInstances = [] } = useQuery({
    queryKey: qk.toolInstances.list({ connector_type: 'data', placement: 'remote', limit: 1000 }),
    queryFn: () => toolInstancesApi.list({ connector_type: 'data', placement: 'remote', limit: 1000 }),
    enabled: isComposerOpen,
    staleTime: 60_000,
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
    return rules.filter((row) => {
      return resolveRbacSearchText(row, agentById, instanceById).includes(q);
    });
  }, [rules, search, agentById, instanceById]);

  const resourceTypeOptions = [
    { value: 'agent', label: 'Агенты' },
    { value: 'tool', label: 'Локальные инструменты' },
    { value: 'instance', label: 'Коннекторы' },
  ];

  const levelOptions = [
    { value: 'platform', label: 'Платформа' },
    { value: 'tenant', label: 'Тенант' },
    { value: 'user', label: 'Пользователь' },
  ];

  const effectOptions = [
    { value: 'deny', label: 'Запрещён' },
    { value: 'allow', label: 'Разрешён' },
  ];

  const ownerOptions = useMemo(() => {
    if (draftLevel === 'platform') {
      return [];
    }
    if (draftLevel === 'tenant') {
      return (tenantsData?.items ?? []).map((tenant) => ({
        value: tenant.id,
        label: tenant.name,
      }));
    }
    return (usersData?.users ?? []).map((user) => ({
      value: user.id,
      label: user.login,
    }));
  }, [draftLevel, tenantsData, usersData]);

  const resourceOptions = useMemo(() => {
    if (draftResourceType === 'agent') {
      return agents.map((agent) => ({
        value: agent.id,
        label: agent.name?.trim() || agent.slug?.trim() || agent.id,
      }));
    }
    if (draftResourceType === 'tool') {
      return localTools
        .filter((tool) => !!tool.tool_id)
        .map((tool) => ({
          value: tool.tool_id!,
          label: tool.name?.trim() || tool.slug?.trim() || tool.tool_id!,
        }));
    }
    return localDataInstances.map((instance) => ({
      value: instance.id,
      label: instance.name?.trim() || instance.slug?.trim() || instance.id,
    }));
  }, [draftResourceType, agents, localTools, localDataInstances]);

  useEffect(() => {
    if (draftLevel === 'platform') {
      setDraftOwnerId('');
      return;
    }
    if (!draftOwnerId && ownerOptions.length > 0) {
      setDraftOwnerId(ownerOptions[0].value);
    }
  }, [draftLevel, draftOwnerId, ownerOptions]);

  useEffect(() => {
    if (!resourceOptions.some((option) => option.value === draftResourceId)) {
      setDraftResourceId(resourceOptions[0]?.value ?? '');
    }
  }, [draftResourceType, resourceOptions, draftResourceId]);

  const createMutation = useMutation({
    mutationFn: (payload: RbacRuleCreate) => rbacApi.createRule(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.rbac.all() });
      showSuccess('Правило создано');
      setIsComposerOpen(false);
      setDraftLevel('tenant');
      setDraftOwnerId('');
      setDraftResourceType('agent');
      setDraftResourceId('');
      setDraftEffect('deny');
    },
    onError: (err: Error) => showError(err.message),
  });

  const columns = buildRbacRuleColumns({
    showOwner: true,
    agentById,
    instanceById,
  });

  const handleOpenComposer = () => setIsComposerOpen(true);

  const handleCloseComposer = () => {
    setIsComposerOpen(false);
    setDraftLevel('tenant');
    setDraftOwnerId('');
    setDraftResourceType('agent');
    setDraftResourceId('');
    setDraftEffect('deny');
  };

  const handleCreateRule = () => {
    if (!draftResourceId) {
      showError('Выберите ресурс');
      return;
    }
    const payload = {
      level: draftLevel,
      resource_type: draftResourceType,
      resource_id: draftResourceId,
      effect: draftEffect,
      owner_platform: draftLevel === 'platform',
      owner_tenant_id: draftLevel === 'tenant' ? draftOwnerId : undefined,
      owner_user_id: draftLevel === 'user' ? draftOwnerId : undefined,
    };
    createMutation.mutate(payload);
  };

  const tabActions = [
    <Button
      key="open"
      variant="primary"
      onClick={handleOpenComposer}
    >
      Добавить правило
    </Button>,
  ];

  return (
    <>
      <EntityPageV2
        title="Права доступа"
        mode="view"
        breadcrumbs={[{ label: 'Права доступа' }]}
        headerActions={
          <Input
            placeholder="Поиск по владельцу, ресурсу или уровню..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        }
      >
        <Tab
          title="Все правила"
          layout="full"
          badge={filteredRules.length}
          actions={tabActions}
        >
          {error && (
            <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: 8, marginBottom: 16 }}>
              Не удалось загрузить RBAC правила
            </div>
          )}
          <DataTable
            columns={columns}
            data={filteredRules}
            keyField="id"
            loading={isLoading}
            emptyText="RBAC правила не найдены"
            paginated
            pageSize={20}
            onRowClick={(row) => navigate(`/admin/rbac/${row.id}`)}
          />
        </Tab>
      </EntityPageV2>

      <FormModal
        open={isComposerOpen}
        title="Добавить RBAC правило"
        onClose={handleCloseComposer}
        onSubmit={handleCreateRule}
        saving={createMutation.isPending}
        submitDisabled={(draftLevel !== 'platform' && !draftOwnerId) || !draftResourceId}
        submitLabel="Добавить"
        size="xl"
      >
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: '140px 1fr 180px 180px 140px',
            alignItems: 'end',
          }}
        >
          <div>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Уровень</div>
            <Select value={draftLevel} onChange={(value) => setDraftLevel(value as typeof draftLevel)} options={levelOptions} />
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Владелец</div>
            <Select
              value={draftOwnerId}
              onChange={setDraftOwnerId}
              options={ownerOptions}
              placeholder={draftLevel === 'platform' ? 'Платформа' : 'Выберите владельца'}
              disabled={draftLevel === 'platform'}
            />
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Ресурс</div>
            <Select value={draftResourceType} onChange={(value) => setDraftResourceType(value as ResourceType)} options={resourceTypeOptions} />
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Значение</div>
            <Select
              value={draftResourceId}
              onChange={setDraftResourceId}
              options={resourceOptions}
              placeholder="Выберите ресурс"
            />
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Эффект</div>
            <Select value={draftEffect} onChange={(value) => setDraftEffect(value as RbacEffect)} options={effectOptions} />
          </div>
        </div>
      </FormModal>
    </>
  );
}

export default RbacListPage;
