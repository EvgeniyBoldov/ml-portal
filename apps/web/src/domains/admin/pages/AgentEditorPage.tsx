/**
 * AgentEditorPage - View/Edit/Create agent
 * 
 * Layout similar to PromptEditorPage:
 * - Left column (1/2): Agent info + Prompts
 * - Right column (1/2): Bindings table + Settings
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  agentsApi, 
  promptsApi, 
  policiesApi,
  limitsApi,
  toolsApi,
  toolInstancesApi,
  toolGroupsApi,
  type AgentCreate, 
  type AgentBindingInput, 
  type AgentBindingResponse,
  type Tool,
  type ToolInstance,
  type ToolGroup,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Select, type SelectOption } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import styles from './PromptEditorPage.module.css';

export function AgentEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  // Determine mode
  const isNew = !slug || slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<AgentCreate>({
    slug: '',
    name: '',
    description: '',
    system_prompt_slug: '',
    policy_id: null,
    limit_id: null,
    capabilities: [],
    supports_partial_mode: false,
    generation_config: {},
    is_active: true,
    enable_logging: true,
    bindings: [],
  });

  // Load prompts for selectors
  const { data: prompts = [] } = useQuery({
    queryKey: qk.prompts.list({}),
    queryFn: () => promptsApi.listPrompts(),
  });

  const systemPrompts = prompts.filter((p: any) => p.type !== 'baseline') || [];

  // Load policies and limits for selectors
  const { data: policies = [] } = useQuery({
    queryKey: qk.policies.list({}),
    queryFn: () => policiesApi.list(),
  });

  const { data: limits = [] } = useQuery({
    queryKey: qk.limits.list({}),
    queryFn: () => limitsApi.list({}),
  });

  // Load tools and tool instances for bindings
  const { data: tools = [] } = useQuery({
    queryKey: qk.tools.list({}),
    queryFn: () => toolsApi.list(),
  });

  const { data: toolInstances = [] } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list(),
  });

  const { data: toolGroups = [] } = useQuery({
    queryKey: qk.toolGroups.list({}),
    queryFn: () => toolGroupsApi.list(),
  });

  const [saving, setSaving] = useState(false);
  const [showAddBinding, setShowAddBinding] = useState(false);
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [newBinding, setNewBinding] = useState<AgentBindingInput>({
    tool_id: '',
    tool_instance_id: '',
    credential_strategy: 'any',
    required: false,
  });

  // Filter tools and instances by selected group
  const filteredTools = selectedGroupId 
    ? tools.filter((t: Tool) => t.tool_group_id === selectedGroupId)
    : tools;
  
  const filteredInstances = selectedGroupId
    ? toolInstances.filter((i: ToolInstance) => i.tool_group_id === selectedGroupId)
    : toolInstances;

  // Load agent data
  const { data: agent, isLoading } = useQuery({
    queryKey: qk.agents.detail(slug!),
    queryFn: () => agentsApi.get(slug!),
    enabled: !isNew,
  });

  // Sync form data
  useEffect(() => {
    if (agent) {
      setFormData({
        slug: agent.slug,
        name: agent.name,
        description: agent.description || '',
        system_prompt_slug: agent.system_prompt_slug,
        policy_id: agent.policy_id || null,
        limit_id: agent.limit_id || null,
        capabilities: agent.capabilities || [],
        supports_partial_mode: agent.supports_partial_mode || false,
        generation_config: agent.generation_config || {},
        is_active: agent.is_active,
        enable_logging: agent.enable_logging,
        bindings: agent.bindings?.map((b: AgentBindingResponse) => ({
          tool_id: b.tool_id,
          tool_instance_id: b.tool_instance_id,
          credential_strategy: b.credential_strategy as AgentBindingInput['credential_strategy'],
          required: b.required,
        })) || [],
      });
    }
  }, [agent]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: () => agentsApi.create(formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list({}) });
      showSuccess('Агент создан');
      navigate('/admin/agents');
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: () => agentsApi.update(slug!, formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.agents.list({}) });
      showSuccess('Агент обновлён');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка обновления'),
  });

  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        await createMutation.mutateAsync();
      } else {
        await updateMutation.mutateAsync();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/agents');
    } else {
      if (agent) {
        setFormData({
          slug: agent.slug,
          name: agent.name,
          description: agent.description || '',
          system_prompt_slug: agent.system_prompt_slug,
          policy_id: agent.policy_id || null,
          limit_id: agent.limit_id || null,
          capabilities: agent.capabilities || [],
          supports_partial_mode: agent.supports_partial_mode || false,
          generation_config: agent.generation_config || {},
          is_active: agent.is_active,
          enable_logging: agent.enable_logging,
          bindings: agent.bindings?.map((b: AgentBindingResponse) => ({
            tool_id: b.tool_id,
            tool_instance_id: b.tool_instance_id,
            credential_strategy: b.credential_strategy as AgentBindingInput['credential_strategy'],
            required: b.required,
          })) || [],
        });
      }
      setSearchParams({});
    }
  };

  const handleFieldChange = (key: string, value: string | boolean | null) => {
    setFormData((prev: AgentCreate) => ({ ...prev, [key]: value }));
  };

  // Binding management
  const handleAddBinding = () => {
    if (!newBinding.tool_id || !newBinding.tool_instance_id) return;
    
    // Check if binding already exists
    const exists = formData.bindings?.some(
      (b: AgentBindingInput) => b.tool_id === newBinding.tool_id && b.tool_instance_id === newBinding.tool_instance_id
    );
    if (exists) {
      showError('Такая привязка уже существует');
      return;
    }

    setFormData((prev: AgentCreate) => ({
      ...prev,
      bindings: [...(prev.bindings || []), { ...newBinding }],
    }));
    setNewBinding({
      tool_id: '',
      tool_instance_id: '',
      credential_strategy: 'inherit',
      required: false,
    });
    setShowAddBinding(false);
  };

  const handleRemoveBinding = (index: number) => {
    setFormData((prev: AgentCreate) => ({
      ...prev,
      bindings: prev.bindings?.filter((_: AgentBindingInput, i: number) => i !== index) || [],
    }));
  };

  // Get tool/instance names for display
  const getToolName = (toolId: string) => {
    const tool = tools.find((t: Tool) => t.id === toolId);
    return tool ? `${tool.slug} (${tool.name})` : toolId;
  };

  const getInstanceName = (instanceId: string) => {
    const instance = toolInstances.find((i: ToolInstance) => i.id === instanceId);
    return instance ? `${instance.slug} (${instance.name})` : instanceId;
  };

  // Field definitions
  const agentFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      required: true,
      disabled: !isNew,
      placeholder: 'network-assistant',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Network Engineer Helper',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание агента...',
      rows: 2,
    },
    {
      key: 'system_prompt_slug',
      label: 'Системный промпт',
      type: 'select',
      required: true,
      options: [
        { value: '', label: 'Выберите промпт...' },
        ...systemPrompts.map((p: { slug: string; name: string }) => ({
          value: p.slug,
          label: p.name,
        })),
      ],
    },
    {
      key: 'policy_id',
      label: 'Политика',
      type: 'select',
      description: 'Правила поведения агента',
      options: [
        { value: '', label: 'Не выбрана' },
        ...policies.map((p: any) => ({
          value: p.id,
          label: `${p.name} (${p.slug})`,
        })),
      ],
    },
    {
      key: 'limit_id',
      label: 'Лимиты',
      type: 'select',
      description: 'Ограничения выполнения (шаги, таймауты)',
      options: [
        { value: '', label: 'Не выбраны' },
        ...limits.map((l: any) => ({
          value: l.id,
          label: `${l.name} (${l.slug})`,
        })),
      ],
    },
  ];

  const settingsFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Активен',
      type: 'boolean',
    },
    {
      key: 'enable_logging',
      label: 'Логирование',
      type: 'boolean',
    },
    {
      key: 'supports_partial_mode',
      label: 'Частичный режим',
      type: 'boolean',
      description: 'Разрешить работу при недоступности некоторых инструментов',
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={agent?.name || 'Новый агент'}
      entityTypeLabel="агента"
      backPath="/admin/agents"
      loading={!isNew && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
    >
      <ContentGrid>
        {/* Agent Info - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Информация об агенте"
          icon="bot"
          editable={isEditable}
          fields={agentFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Bindings Table - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Привязки инструментов"
          icon="link"
        >
          {formData.bindings && formData.bindings.length > 0 ? (
            <div className={styles.versionsTable}>
              <table>
                <thead>
                  <tr>
                    <th>Инструмент</th>
                    <th>Инстанс</th>
                    <th>Стратегия</th>
                    <th>Обяз.</th>
                    {isEditable && <th></th>}
                  </tr>
                </thead>
                <tbody>
                  {formData.bindings.map((binding: AgentBindingInput, index: number) => (
                    <tr key={`${binding.tool_id}-${binding.tool_instance_id}`}>
                      <td>{getToolName(binding.tool_id)}</td>
                      <td>{getInstanceName(binding.tool_instance_id)}</td>
                      <td>
                        <Badge variant="default" size="small">
                          {{
                            user_only: 'Личные',
                            tenant_only: 'Тенанта',
                            default_only: 'Общие',
                            prefer_user: 'Предп. личные',
                            prefer_tenant: 'Предп. тенанта',
                            any: 'Любые',
                          }[binding.credential_strategy] || binding.credential_strategy}
                        </Badge>
                      </td>
                      <td>
                        <Badge variant={binding.required ? 'warning' : 'default'} size="small">
                          {binding.required ? 'Да' : 'Нет'}
                        </Badge>
                      </td>
                      {isEditable && (
                        <td>
                          <Button
                            variant="ghost"
                            size="small"
                            onClick={() => handleRemoveBinding(index)}
                          >
                            ✕
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
              Нет привязанных инструментов
            </p>
          )}

          {/* Add binding form */}
          {isEditable && (
            <div style={{ marginTop: '1rem' }}>
              {showAddBinding ? (
                <div style={{ 
                  display: 'flex', 
                  flexDirection: 'column', 
                  gap: '0.75rem',
                  padding: '1rem',
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: '8px',
                  border: '1px solid rgba(255, 255, 255, 0.06)'
                }}>
                  <div style={{ fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.25rem' }}>
                    Новая привязка инструмента
                  </div>
                  
                  {/* Group filter */}
                  <div>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.25rem', display: 'block' }}>
                      Группа (фильтр)
                    </label>
                    <Select
                      value={selectedGroupId}
                      onChange={(value) => {
                        setSelectedGroupId(value);
                        setNewBinding({ ...newBinding, tool_id: '', tool_instance_id: '' });
                      }}
                      placeholder="Все группы"
                      options={[
                        { value: '', label: 'Все группы' },
                        ...toolGroups.map((g: ToolGroup) => ({ value: g.id, label: g.name }))
                      ]}
                    />
                  </div>

                  {/* Tool select */}
                  <div>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.25rem', display: 'block' }}>
                      Инструмент *
                    </label>
                    <Select
                      value={newBinding.tool_id}
                      onChange={(value) => setNewBinding({ ...newBinding, tool_id: value, tool_instance_id: '' })}
                      placeholder="Выберите инструмент..."
                      options={[
                        { value: '', label: 'Выберите инструмент...' },
                        ...filteredTools.map((t: Tool) => ({ value: t.id, label: `${t.slug} — ${t.name}` }))
                      ]}
                    />
                  </div>

                  {/* Instance select */}
                  <div>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.25rem', display: 'block' }}>
                      Инстанс *
                    </label>
                    <Select
                      value={newBinding.tool_instance_id}
                      onChange={(value) => setNewBinding({ ...newBinding, tool_instance_id: value })}
                      placeholder="Выберите инстанс..."
                      options={[
                        { value: '', label: 'Выберите инстанс...' },
                        ...filteredInstances.map((i: ToolInstance) => ({ value: i.id, label: `${i.slug} — ${i.name}` }))
                      ]}
                    />
                  </div>

                  {/* Credential strategy - уровень прав */}
                  <div>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.25rem', display: 'block' }}>
                      Уровень прав
                    </label>
                    <Select
                      value={newBinding.credential_strategy}
                      onChange={(value) => setNewBinding({ ...newBinding, credential_strategy: value as AgentBindingInput['credential_strategy'] })}
                      options={[
                        { value: 'any', label: 'Любые (по умолчанию)' },
                        { value: 'user_only', label: 'Только личные' },
                        { value: 'tenant_only', label: 'Только тенанта' },
                        { value: 'default_only', label: 'Только общие' },
                        { value: 'prefer_user', label: 'Предпочитать личные' },
                        { value: 'prefer_tenant', label: 'Предпочитать тенанта' },
                      ]}
                    />
                  </div>

                  {/* Required checkbox */}
                  <label style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '0.5rem',
                    fontSize: '0.875rem',
                    cursor: 'pointer'
                  }}>
                    <input
                      type="checkbox"
                      checked={newBinding.required}
                      onChange={(e) => setNewBinding({ ...newBinding, required: e.target.checked })}
                      style={{ width: '16px', height: '16px' }}
                    />
                    Обязательный инструмент
                  </label>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                    <Button variant="primary" size="small" onClick={handleAddBinding}>
                      Добавить
                    </Button>
                    <Button variant="ghost" size="small" onClick={() => {
                      setShowAddBinding(false);
                      setSelectedGroupId('');
                      setNewBinding({ tool_id: '', tool_instance_id: '', credential_strategy: 'any', required: false });
                    }}>
                      Отмена
                    </Button>
                  </div>
                </div>
              ) : (
                <Button variant="ghost" size="small" onClick={() => setShowAddBinding(true)}>
                  + Добавить привязку
                </Button>
              )}
            </div>
          )}
        </ContentBlock>

        {/* Settings - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Настройки"
          icon="settings"
          editable={isEditable}
          fields={settingsFields}
          data={formData}
          onChange={handleFieldChange}
        />
      </ContentGrid>
    </EntityPage>
  );
}

export default AgentEditorPage;
