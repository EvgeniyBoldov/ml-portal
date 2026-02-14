/**
 * AgentVersionPage - View/Edit/Create agent version
 *
 * Two tabs:
 * 1. Overview - prompt, status, policy selector, limit selector, notes
 * 2. Bindings - tool bindings table (read-only for now, managed via API)
 */
import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  agentsApi,
  policiesApi,
  limitsApi,
  toolReleasesApi,
  toolInstancesApi,
  type AgentVersionCreate,
  type AgentBindingResponse,
  type AgentBindingCreate,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  EntityPageV2,
  Tab,
  type EntityPageMode,
  type BreadcrumbItem,
} from '@/shared/ui/EntityPage/EntityPageV2';
import {
  ContentBlock,
  Textarea,
  Badge,
  Select,
  DataTable,
  Button,
  type DataTableColumn,
} from '@/shared/ui';

export function AgentVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam || '0', 10);
  const isEditMode = searchParams.get('mode') === 'edit';
  const fromVersion = searchParams.get('from');
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState({ prompt: '', policy_id: '', limit_id: '', notes: '' });
  const [saving, setSaving] = useState(false);

  // Load agent container
  const { data: agent } = useQuery({
    queryKey: qk.agents.detail(slug!),
    queryFn: () => agentsApi.get(slug!),
    enabled: !!slug,
  });

  // Load existing version
  const { data: existingVersion, isLoading } = useQuery({
    queryKey: qk.agents.version(slug!, versionNumber),
    queryFn: () => agentsApi.getVersion(slug!, versionNumber),
    enabled: !isCreate && !!slug && versionNumber > 0,
  });

  // Load source version for duplication
  const fromVersionNumber = fromVersion ? parseInt(fromVersion, 10) : 0;
  const { data: sourceVersion } = useQuery({
    queryKey: qk.agents.version(slug!, fromVersionNumber),
    queryFn: () => agentsApi.getVersion(slug!, fromVersionNumber),
    enabled: isCreate && !!slug && fromVersionNumber > 0,
  });

  // Load policies and limits for selectors
  const { data: policies = [] } = useQuery({
    queryKey: qk.policies.list({}),
    queryFn: () => policiesApi.list(),
    staleTime: 300000,
  });

  const { data: limits = [] } = useQuery({
    queryKey: qk.limits.list({}),
    queryFn: () => limitsApi.list(),
    staleTime: 300000,
  });

  // Form data initialization
  useEffect(() => {
    if (isCreate && sourceVersion) {
      setFormData({
        prompt: sourceVersion.prompt,
        policy_id: sourceVersion.policy_id || '',
        limit_id: sourceVersion.limit_id || '',
        notes: sourceVersion.notes || '',
      });
    } else if (!isCreate && existingVersion) {
      setFormData({
        prompt: existingVersion.prompt,
        policy_id: existingVersion.policy_id || '',
        limit_id: existingVersion.limit_id || '',
        notes: existingVersion.notes || '',
      });
    }
  }, [existingVersion, isCreate, sourceVersion]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: AgentVersionCreate) => agentsApi.createVersion(slug!, data),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      showSuccess('Версия создана');
      navigate(`/admin/agents/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => agentsApi.updateVersion(slug!, versionNumber, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.version(slug!, versionNumber) });
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      showSuccess('Версия обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => agentsApi.activateVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.agents.version(slug!, versionNumber) });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => agentsApi.deactivateVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.agents.version(slug!, versionNumber) });
      showSuccess('Версия деактивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  // Form actions
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isCreate) {
        const data: AgentVersionCreate = {
          prompt: formData.prompt,
          policy_id: formData.policy_id || null,
          limit_id: formData.limit_id || null,
          notes: formData.notes || null,
        };
        if (sourceVersion) {
          data.parent_version_id = sourceVersion.id;
        }
        await createMutation.mutateAsync(data);
      } else {
        await updateMutation.mutateAsync({
          prompt: formData.prompt,
          policy_id: formData.policy_id || null,
          limit_id: formData.limit_id || null,
          notes: formData.notes || null,
        });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    if (existingVersion?.status !== 'draft') {
      showError('Редактировать можно только черновики');
      return;
    }
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (isCreate) {
      navigate(`/admin/agents/${slug}`);
    } else {
      if (existingVersion) {
        setFormData({
          prompt: existingVersion.prompt,
          policy_id: existingVersion.policy_id || '',
          limit_id: existingVersion.limit_id || '',
          notes: existingVersion.notes || '',
        });
      }
      setSearchParams({});
    }
  };

  // Breadcrumbs
  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Агенты', href: '/admin/agents' },
    { label: agent?.name || slug || '', href: `/admin/agents/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const isCurrent = !!(agent?.current_version_id && existingVersion?.id && agent.current_version_id === existingVersion.id);

  // Create version action buttons as array (not ReactNode)
  const createVersionActionButtons = () => {
    const buttons = [];
    const status = existingVersion?.status;

    if (status === 'draft') {
      buttons.push(
        <Button key="edit" variant="outline" onClick={handleEdit}>
          Редактировать
        </Button>
      );
      buttons.push(
        <Button
          key="activate"
          variant="primary"
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
        >
          Активировать
        </Button>
      );
    } else if (status === 'active') {
      buttons.push(
        <Button
          key="deactivate"
          variant="outline"
          onClick={() => deactivateMutation.mutate()}
          disabled={deactivateMutation.isPending}
        >
          Деактивировать
        </Button>
      );
    } else if (status === 'inactive' || status === 'archived') {
      buttons.push(
        <Button
          key="reactivate"
          variant="primary"
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
        >
          Активировать
        </Button>
      );
    }

    // Duplicate button for all statuses
    buttons.push(
      <Button
        key="duplicate"
        variant="outline"
        onClick={() => navigate(`/admin/agents/${slug}/versions/new?from=${versionNumber}`)}
      >
        Дублировать
      </Button>
    );

    return buttons;
  };

  // Prepare dropdown options
  const policyOptions = useMemo(() => {
    return policies.map((p: any) => ({
      value: p.id,
      label: `${p.name} (${p.slug})`,
    }));
  }, [policies]);

  const limitOptions = useMemo(() => {
    return limits.map((l: any) => ({
      value: l.id,
      label: `${l.name} (${l.slug})`,
    }));
  }, [limits]);

  // Helper functions
  const getPolicyName = (id: string) => {
    const p = policies.find((p: any) => p.id === id);
    return p ? `${p.name} (${p.slug})` : '—';
  };

  const getLimitName = (id: string) => {
    const l = limits.find((l: any) => l.id === id);
    return l ? `${l.name} (${l.slug})` : '—';
  };

  // ─── Bindings ───────────────────────────────────────────────────────────
  const [showAddBinding, setShowAddBinding] = useState(false);
  const [newBindingToolId, setNewBindingToolId] = useState('');
  const [newBindingInstanceId, setNewBindingInstanceId] = useState('');
  const [newBindingStrategy, setNewBindingStrategy] = useState('ANY');

  const { data: bindings = [], isLoading: bindingsLoading } = useQuery({
    queryKey: qk.agents.bindings(slug!, versionNumber),
    queryFn: () => agentsApi.listBindings(slug!, versionNumber),
    enabled: !isCreate && !!slug && versionNumber > 0,
  });

  // Load tool groups with tools for the selector
  const { data: toolGroups = [] } = useQuery({
    queryKey: ['tool-groups-list'],
    queryFn: () => toolReleasesApi.listGroups(),
    staleTime: 300000,
  });

  // Flatten tools from all groups
  const [allTools, setAllTools] = useState<{ id: string; slug: string; name: string; group: string }[]>([]);
  useEffect(() => {
    const loadTools = async () => {
      const tools: { id: string; slug: string; name: string; group: string }[] = [];
      for (const g of toolGroups) {
        try {
          const groupTools = await toolReleasesApi.listToolsByGroup(g.slug);
          for (const t of groupTools) {
            tools.push({ id: t.id, slug: t.slug, name: t.name, group: g.slug });
          }
        } catch { /* skip */ }
      }
      setAllTools(tools);
    };
    if (toolGroups.length > 0) loadTools();
  }, [toolGroups]);

  // Load instances for selector
  const { data: allInstances = [] } = useQuery({
    queryKey: ['tool-instances-list'],
    queryFn: () => toolInstancesApi.list({ limit: 200 }),
    staleTime: 300000,
  });

  const addBindingMutation = useMutation({
    mutationFn: (data: AgentBindingCreate) =>
      agentsApi.createBinding(slug!, versionNumber, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.bindings(slug!, versionNumber) });
      showSuccess('Привязка добавлена');
      setShowAddBinding(false);
      setNewBindingToolId('');
      setNewBindingInstanceId('');
      setNewBindingStrategy('ANY');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteBindingMutation = useMutation({
    mutationFn: (bindingId: string) =>
      agentsApi.deleteBinding(slug!, versionNumber, bindingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.bindings(slug!, versionNumber) });
      showSuccess('Привязка удалена');
    },
    onError: (err: Error) => showError(err.message),
  });

  const handleAddBinding = () => {
    if (!newBindingToolId) {
      showError('Выберите инструмент');
      return;
    }
    addBindingMutation.mutate({
      agent_version_id: existingVersion!.id,
      tool_id: newBindingToolId,
      tool_instance_id: newBindingInstanceId || null,
      credential_strategy: newBindingStrategy,
    });
  };

  // Available tools (not yet bound)
  const boundToolIds = new Set(bindings.map((b) => b.tool_id));
  const availableTools = allTools.filter((t) => !boundToolIds.has(t.id));

  const toolOptions = availableTools.map((t) => ({
    value: t.id,
    label: `${t.group} / ${t.name} (${t.slug})`,
  }));

  const instanceOptions = [
    { value: '', label: '— Без привязки к инстансу —' },
    ...allInstances.map((i) => ({
      value: i.id,
      label: `${i.name} (${i.slug})`,
    })),
  ];

  const strategyOptions = [
    { value: 'ANY', label: 'ANY — первый доступный' },
    { value: 'USER_ONLY', label: 'USER_ONLY' },
    { value: 'TENANT_ONLY', label: 'TENANT_ONLY' },
    { value: 'PLATFORM_ONLY', label: 'PLATFORM_ONLY' },
    { value: 'USER_THEN_TENANT', label: 'USER_THEN_TENANT' },
    { value: 'TENANT_THEN_PLATFORM', label: 'TENANT_THEN_PLATFORM' },
  ];

  // Binding columns
  const bindingColumns: DataTableColumn<AgentBindingResponse>[] = [
    {
      key: 'tool_slug',
      label: 'Инструмент',
      render: (b) => (
        <div>
          <div style={{ fontWeight: 500 }}>{b.tool_name || b.tool_slug || '—'}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {b.tool_group_slug ? `${b.tool_group_slug} / ` : ''}{b.tool_slug}
          </div>
        </div>
      ),
    },
    {
      key: 'instance_slug',
      label: 'Инстанс',
      render: (b) => (
        b.instance_name
          ? <span>{b.instance_name} <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>({b.instance_slug})</span></span>
          : <span style={{ color: 'var(--text-secondary)' }}>—</span>
      ),
    },
    {
      key: 'credential_strategy',
      label: 'Стратегия',
      render: (b) => (
        <Badge tone="neutral" size="small">{b.credential_strategy}</Badge>
      ),
    },
    {
      key: 'actions',
      label: '',
      render: (b) => (
        <Button
          variant="ghost"
          size="small"
          onClick={() => {
            if (confirm('Удалить привязку?')) {
              deleteBindingMutation.mutate(b.id);
            }
          }}
        >
          ✕
        </Button>
      ),
    },
  ];

  // Create mode — single tab
  if (isCreate) {
    return (
      <EntityPageV2
        title="Новая версия"
        mode={mode}
        backPath={`/admin/agents/${slug}`}
        breadcrumbs={breadcrumbs}
        saving={saving}
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="single">
          <ContentBlock
            title="Системный промпт"
            icon="file-text"
          >
            {isEditable ? (
              <Textarea
                value={formData.prompt}
                onChange={(e) => setFormData(prev => ({ ...prev, prompt: e.target.value }))}
                placeholder="Введите системный промпт агента..."
                rows={16}
                style={{ fontFamily: 'monospace' }}
              />
            ) : (
              <pre style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                lineHeight: '1.5',
                margin: 0,
              }}>
                {formData.prompt || 'Нет промпта'}
              </pre>
            )}
          </ContentBlock>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
            <ContentBlock title="Политика" icon="shield">
              {isEditable ? (
                <Select
                  value={formData.policy_id}
                  onChange={(value) => setFormData(prev => ({ ...prev, policy_id: value }))}
                  options={policyOptions}
                  placeholder="Выберите политику..."
                />
              ) : (
                <span style={{ fontSize: '0.875rem' }}>
                  {formData.policy_id ? getPolicyName(formData.policy_id) : '—'}
                </span>
              )}
            </ContentBlock>

            <ContentBlock title="Лимиты" icon="gauge">
              {isEditable ? (
                <Select
                  value={formData.limit_id}
                  onChange={(value) => setFormData(prev => ({ ...prev, limit_id: value }))}
                  options={limitOptions}
                  placeholder="Выберите лимиты..."
                />
              ) : (
                <span style={{ fontSize: '0.875rem' }}>
                  {formData.limit_id ? getLimitName(formData.limit_id) : '—'}
                </span>
              )}
            </ContentBlock>
          </div>

          <ContentBlock title="Заметки" icon="file-text" style={{ marginTop: '1rem' }}>
            {isEditable ? (
              <Textarea
                value={formData.notes}
                onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                placeholder="Описание изменений..."
                rows={3}
                style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}
              />
            ) : (
              <pre style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                lineHeight: '1.5',
                margin: 0,
              }}>
                {formData.notes || 'Нет заметок'}
              </pre>
            )}
          </ContentBlock>
        </Tab>
      </EntityPageV2>
    );
  }

  // View/Edit mode — two tabs
  return (
    <EntityPageV2
      title={`Версия ${versionNumber}`}
      mode={mode}
      backPath={`/admin/agents/${slug}`}
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      saving={saving}
    >
      <Tab 
        title="Обзор" 
        layout="single"
        actions={
          mode === 'view' ? createVersionActionButtons() : mode === 'edit' ? [
            <Button key="save" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : []
        }
      >
        <ContentBlock
          title="Системный промпт"
          icon="file-text"
          headerActions={
            existingVersion?.status ? (
              <Badge tone={existingVersion.status === 'active' ? 'success' : existingVersion.status === 'draft' ? 'warn' : 'neutral'} size="small">
                {existingVersion.status === 'active' ? 'Активна' : existingVersion.status === 'draft' ? 'Черновик' : 'Архив'}
              </Badge>
            ) : undefined
          }
        >
          {isEditable ? (
            <Textarea
              value={formData.prompt}
              onChange={(e) => setFormData(prev => ({ ...prev, prompt: e.target.value }))}
              placeholder="Введите системный промпт агента..."
              rows={16}
              style={{ fontFamily: 'monospace' }}
            />
          ) : (
            <pre style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              lineHeight: '1.5',
              margin: 0,
            }}>
              {existingVersion?.prompt || 'Нет промпта'}
            </pre>
          )}
        </ContentBlock>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
          <ContentBlock title="Политика" icon="shield">
            {isEditable ? (
              <Select
                value={formData.policy_id}
                onChange={(value) => setFormData(prev => ({ ...prev, policy_id: value }))}
                options={policyOptions}
                placeholder="Выберите политику..."
              />
            ) : (
              <span style={{ fontSize: '0.875rem' }}>
                {formData.policy_id ? getPolicyName(formData.policy_id) : '—'}
              </span>
            )}
          </ContentBlock>

          <ContentBlock title="Лимиты" icon="gauge">
            {isEditable ? (
              <Select
                value={formData.limit_id}
                onChange={(value) => setFormData(prev => ({ ...prev, limit_id: value }))}
                options={limitOptions}
                placeholder="Выберите лимиты..."
              />
            ) : (
              <span style={{ fontSize: '0.875rem' }}>
                {formData.limit_id ? getLimitName(formData.limit_id) : '—'}
              </span>
            )}
          </ContentBlock>
        </div>

        <ContentBlock title="Заметки" icon="file-text" style={{ marginTop: '1rem' }}>
          {isEditable ? (
            <Textarea
              value={formData.notes}
              onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
              placeholder="Описание изменений..."
              rows={3}
              style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}
            />
          ) : (
            <pre style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              lineHeight: '1.5',
              margin: 0,
            }}>
              {formData.notes || 'Нет заметок'}
            </pre>
          )}
        </ContentBlock>
      </Tab>

      <Tab 
        title="Привязки" 
        layout="full"
        badge={bindings.length}
        actions={[
          <Button key="add-tool" variant="outline" onClick={() => setShowAddBinding(!showAddBinding)}>
            {showAddBinding ? 'Отмена' : 'Добавить инструмент'}
          </Button>,
        ]}
      >
        {showAddBinding && (
          <ContentBlock title="Новая привязка" icon="plus" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '0.75rem', alignItems: 'end' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 500, marginBottom: '0.25rem', color: 'var(--text-secondary)' }}>Инструмент</label>
                <Select
                  value={newBindingToolId}
                  onChange={(v) => setNewBindingToolId(v)}
                  options={toolOptions}
                  placeholder="Выберите инструмент..."
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 500, marginBottom: '0.25rem', color: 'var(--text-secondary)' }}>Инстанс</label>
                <Select
                  value={newBindingInstanceId}
                  onChange={(v) => setNewBindingInstanceId(v)}
                  options={instanceOptions}
                  placeholder="Выберите инстанс..."
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 500, marginBottom: '0.25rem', color: 'var(--text-secondary)' }}>Стратегия</label>
                <Select
                  value={newBindingStrategy}
                  onChange={(v) => setNewBindingStrategy(v)}
                  options={strategyOptions}
                />
              </div>
              <Button
                onClick={handleAddBinding}
                disabled={addBindingMutation.isPending || !newBindingToolId}
              >
                {addBindingMutation.isPending ? 'Добавление...' : 'Добавить'}
              </Button>
            </div>
          </ContentBlock>
        )}
        <DataTable
          columns={bindingColumns}
          data={bindings}
          keyField="id"
          loading={bindingsLoading}
          emptyText="Нет привязок инструментов для этой версии"
        />
      </Tab>
    </EntityPageV2>
  );
}

export default AgentVersionPage;
