/**
 * AgentVersionPage v2 - View/Edit/Create agent version
 *
 * Two tabs:
 * 1. Overview - prompt, status, policy selector, limit selector, notes
 * 2. Bindings - tool bindings table (read-only for now, managed via API)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  agentsApi,
  policiesApi,
  limitsApi,
  type AgentVersionCreate,
  type AgentBindingResponse,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  EntityPage,
  ContentBlock,
  Textarea,
  Badge,
  Select,
  DataTable,
  Tabs,
  TabPanel,
  type EntityPageMode,
  type BreadcrumbItem,
  type DataTableColumn,
} from '@/shared/ui';
import { useVersionActions } from '@/shared/hooks/useVersionActions';

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

  const [activeTab, setActiveTab] = useState('overview');
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
  });

  const { data: limits = [] } = useQuery({
    queryKey: qk.limits.list({}),
    queryFn: () => limitsApi.list({}),
  });

  useEffect(() => {
    if (isCreate && sourceVersion) {
      setFormData({
        prompt: sourceVersion.prompt || '',
        policy_id: sourceVersion.policy_id || '',
        limit_id: sourceVersion.limit_id || '',
        notes: '',
      });
    } else if (isCreate) {
      setFormData({ prompt: '', policy_id: '', limit_id: '', notes: '' });
    } else if (existingVersion) {
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

  const handleSave = async () => {
    if (!formData.prompt.trim()) {
      showError('Промпт не может быть пустым');
      return;
    }
    setSaving(true);
    try {
      const data: AgentVersionCreate = {
        prompt: formData.prompt,
        policy_id: formData.policy_id || null,
        limit_id: formData.limit_id || null,
        notes: formData.notes || null,
      };
      if (isCreate) {
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

  const handleEdit = () => setSearchParams({ mode: 'edit' });

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

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Агенты', href: '/admin/agents' },
    { label: agent?.name || slug || '', href: `/admin/agents/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const isCurrent = !!(agent?.current_version_id && existingVersion?.id && agent.current_version_id === existingVersion.id);

  const actionButtons = useVersionActions({
    status: existingVersion?.status,
    isRecommended: isCurrent,
    isCreate,
    callbacks: {
      onEdit: () => setSearchParams({ mode: 'edit' }),
      onActivate: () => activateMutation.mutate(),
      onDeactivate: () => deactivateMutation.mutate(),
      onDuplicate: () => navigate(`/admin/agents/${slug}/versions/new?from=${versionNumber}`),
    },
    loading: {
      activate: activateMutation.isPending,
      deactivate: deactivateMutation.isPending,
    },
  });

  // Bindings columns
  const bindingColumns: DataTableColumn<AgentBindingResponse>[] = [
    {
      key: 'tool_id',
      label: 'TOOL ID',
      render: (b) => (
        <code style={{ fontSize: '0.8125rem' }}>{b.tool_id}</code>
      ),
    },
    {
      key: 'tool_instance_id',
      label: 'INSTANCE ID',
      render: (b) => b.tool_instance_id ? (
        <code style={{ fontSize: '0.8125rem' }}>{b.tool_instance_id}</code>
      ) : (
        <span style={{ color: 'var(--text-secondary)' }}>—</span>
      ),
    },
    {
      key: 'credential_strategy',
      label: 'СТРАТЕГИЯ',
      width: 140,
      render: (b) => (
        <Badge tone="neutral" size="small">{b.credential_strategy}</Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      width: 120,
      render: (b) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
          {new Date(b.created_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
  ];

  // Policy/Limit options
  const policyOptions = [
    { value: '', label: 'Не выбрана' },
    ...policies.map((p: any) => ({ value: p.id, label: `${p.name} (${p.slug})` })),
  ];

  const limitOptions = [
    { value: '', label: 'Не выбраны' },
    ...limits.map((l: any) => ({ value: l.id, label: `${l.name} (${l.slug})` })),
  ];

  const getPolicyName = (id: string) => {
    const p = policies.find((p: any) => p.id === id);
    return p ? `${p.name} (${p.slug})` : '—';
  };

  const getLimitName = (id: string) => {
    const l = limits.find((l: any) => l.id === id);
    return l ? `${l.name} (${l.slug})` : '—';
  };

  // Tabs for non-create mode
  const tabs = [
    { id: 'overview', label: 'Обзор' },
    { id: 'bindings', label: 'Привязки' },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новая версия' : `Версия ${versionNumber}`}
      entityTypeLabel="версии"
      backPath={`/admin/agents/${slug}`}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      actionButtons={actionButtons}
      tabsBar={!isCreate && (
        <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border-color)' }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '0.75rem 1.25rem',
                background: 'none',
                border: 'none',
                borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
                color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontWeight: activeTab === tab.id ? 500 : 400,
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}
      noPadding={!isCreate}
    >
      {(isCreate || activeTab === 'overview') && (
        <div style={{ padding: isCreate ? 0 : '1.5rem' }}>
          <ContentBlock
            title="Системный промпт"
            icon="file-text"
            headerActions={
              !isCreate && existingVersion?.status ? (
                <Badge
                  tone={existingVersion.status === 'active' ? 'success' : existingVersion.status === 'draft' ? 'warn' : 'neutral'}
                  size="small"
                >
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
        </div>
      )}

      {!isCreate && activeTab === 'bindings' && (
        <div style={{ padding: '1.5rem' }}>
          <ContentBlock title="Привязки инструментов" icon="link">
            <DataTable
              columns={bindingColumns}
              data={(existingVersion as any)?.bindings || []}
              keyField="id"
              emptyText="Нет привязок инструментов для этой версии"
            />
          </ContentBlock>
        </div>
      )}
    </EntityPage>
  );
}

export default AgentVersionPage;
