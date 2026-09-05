/**
 * PlatformSettingsPage - Global platform configuration (singleton)
 *
 * Tabs: Модели | Ограничения | Фолбеки | Лимиты | Общие доступы | RBAC
 * Uses EntityPageV2 + Tab architecture.
 */
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { credentialsApi } from '@/shared/api/credentials';
import { adminApi, type Model, type ModelListResponse, type PlatformSettings, type PlatformSettingsUpdate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { DataTable, type DataTableColumn, Badge, Button } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { ADMIN_ACTION_LABELS, ADMIN_ENTITY_LABELS } from '@/shared/constants/adminLabels';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable/RBACRulesTable';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { usePlatformSettings, useUpdatePlatformSettings, useFillPlatformSettingsDefaults, usePlatformExecutionLimits, useUpdatePlatformExecutionLimits, useAgentDefaultExecutionLimits, useUpdateAgentDefaultExecutionLimits, useOrchestratorDefaultExecutionLimits, useUpdateOrchestratorDefaultExecutionLimits } from '@/shared/api/hooks/usePlatformSettings';
import { useState } from 'react';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';

/* ─── Field configs ─── */

// Policy Text field
const POLICY_TEXT_FIELDS: FieldConfig[] = [
  {
    key: 'policies_text',
    type: 'textarea',
    label: 'Политики (markdown)',
    description: 'Текст правил для planner и executor. Подмешивается в системные промпты.',
    rows: 8,
    placeholder: '# Правила платформы\n\n## Безопасность\n- Все write операции требуют подтверждения\n- Destructive операции запрещены...\n',
  },
];

// Policy Gates fields
const POLICY_GATES_FIELDS: FieldConfig[] = [
  {
    key: 'require_confirmation_for_write',
    type: 'boolean',
    label: 'Требовать подтверждения для write',
    description: 'Все операции записи требуют подтверждения',
  },
  {
    key: 'require_confirmation_for_destructive',
    type: 'boolean',
    label: 'Требовать подтверждения для destructive',
    description: 'Разрушительные операции требуют подтверждения',
  },
  {
    key: 'forbid_destructive',
    type: 'boolean',
    label: 'Запретить destructive операции',
    description: 'Полностью запретить разрушительные операции',
  },
  {
    key: 'forbid_write_in_prod',
    type: 'boolean',
    label: 'Запретить write в production',
    description: 'Запретить операции записи в production окружении',
  },
  {
    key: 'require_backup_before_write',
    type: 'boolean',
    label: 'Требовать бэкап перед write',
    description: 'Требовать создание бэкапа перед операциями записи',
  },
];

const FALLBACK_RUNTIME_RULES_FIELDS: FieldConfig[] = [
  {
    key: 'required_operation_retry_instruction',
    type: 'textarea',
    label: 'Инструкция повтора операции',
    description: 'Текст, который подмешивается в протокол, если агент ответил без обязательного operation_call.',
    rows: 4,
    placeholder: 'Необходимо вызвать хотя бы одну операцию перед ответом...',
  },
  {
    key: 'operations_rules_text',
    type: 'textarea',
    label: 'Правила операций',
    description: 'Полная замена блока обязательных правил для prompt с operations.',
    rows: 8,
    placeholder: 'ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА — соблюдай без исключений...',
  },
  {
    key: 'intent_messages',
    type: 'json',
    label: 'Сообщения намерений',
    description: 'JSON-словарь для runtime intent messages: agent_start, final_answer, operation_call.',
    rows: 6,
  },
];

const FALLBACK_NUMERIC_FIELDS: FieldConfig[] = [
  {
    key: 'default_max_iters',
    type: 'number',
    label: 'Max iters по умолчанию',
    description: 'Используется, если execution limits не задали лимит шагов агента.',
  },
];

const RUN_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'wall_time_ms_max', type: 'number', label: 'Wall time (ms)', description: 'Максимальное время выполнения run.' },
  { key: 'max_parallel_tasks', type: 'number', label: 'Параллельные задачи', description: 'Максимум одновременно исполняемых задач.' },
  { key: 'max_replans', type: 'number', label: 'Перепланирования', description: 'Максимум перепланирований после первоначального плана.' },
  { key: 'max_task_executions', type: 'number', label: 'Запуски задач', description: 'Максимум фактических запусков задач, включая повторы.' },
];

const AGENT_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'llm_calls_max', type: 'number', label: 'LLM-вызовы', description: 'Default на один запуск агента.' },
  { key: 'tool_calls_max', type: 'number', label: 'Tool-вызовы', description: 'Default на один запуск агента.' },
  { key: 'wall_time_ms_max', type: 'number', label: 'Wall time (ms)', description: 'Default на один запуск агента.' },
];

const ORCHESTRATOR_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'llm_calls_max', type: 'number', label: 'LLM-вызовы', description: 'Default на один запуск роли.' },
  { key: 'wall_time_ms_max', type: 'number', label: 'Wall time (ms)', description: 'Default на один запуск роли.' },
];

const CHAT_UPLOAD_FIELDS: FieldConfig[] = [
  {
    key: 'chat_upload_max_bytes',
    type: 'number',
    label: 'Макс. размер файла (байт)',
    description: 'Ограничение размера файлов для загрузки в чат',
    placeholder: '52428800',
  },
  {
    key: 'chat_upload_allowed_extensions',
    type: 'text',
    label: 'Разрешенные расширения',
    description: 'Список через запятую, например: txt,md,pdf,doc,docx,xls,xlsx,csv',
    placeholder: 'txt,md,pdf,doc,docx,xls,xlsx,csv',
  },
];

const MODEL_FIELDS: DataTableColumn<Model>[] = [
  {
    key: 'alias',
    label: 'АЛИАС / НАЗВАНИЕ',
    sortable: true,
    render: (m: Model) => (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        <span style={{ fontWeight: 500 }}>{m.alias}</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{m.name}</span>
      </div>
    ),
  },
  {
    key: 'type',
    label: 'ТИП',
    width: 110,
    render: (m: Model) => {
      const toneMap: Record<string, 'info' | 'success' | 'warn'> = {
        llm_chat: 'info',
        embedding: 'success',
        reranker: 'warn',
      };
      const labelMap: Record<string, string> = {
        llm_chat: 'LLM Chat',
        embedding: 'Embedding',
        reranker: 'Reranker',
      };
      return <Badge tone={toneMap[m.type] ?? 'info'}>{labelMap[m.type] ?? m.type}</Badge>;
    },
  },
  {
    key: 'connector',
    label: 'КОННЕКТОР',
    sortable: true,
    render: (m: Model) => (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        <span style={{ fontWeight: 500 }}>{m.connector}</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{m.provider_model_name}</span>
      </div>
    ),
  },
  {
    key: 'status',
    label: 'СТАТУС',
    width: 120,
    render: (m: Model) => {
      const toneMap: Record<string, 'success' | 'warn' | 'danger' | 'neutral'> = {
        available: 'success',
        unavailable: 'danger',
        deprecated: 'neutral',
        maintenance: 'warn',
      };
      const labelMap: Record<string, string> = {
        available: 'Доступна',
        unavailable: 'Недоступна',
        deprecated: 'Устарела',
        maintenance: 'Обслуживание',
      };
      return <Badge tone={toneMap[m.status] ?? 'neutral'}>{labelMap[m.status] ?? m.status}</Badge>;
    },
  },
  {
    key: 'default_for_type',
    label: 'ПО УМОЛЧ.',
    width: 100,
    render: (m: Model) => m.default_for_type ? (
      <Badge tone="success">По умолч.</Badge>
    ) : (
      <span style={{ color: 'var(--text-secondary)' }}>—</span>
    ),
  },
];

export function PlatformSettingsPage() {
  const navigate = useNavigate();
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingUpdates, setPendingUpdates] = useState<PlatformSettingsUpdate | null>(null);
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [formData, setFormData] = useState<Partial<PlatformSettings>>({});

  // Limits tab — execution limits
  const [limitsMode, setLimitsMode] = useState<'view' | 'edit'>('view');
  const [limitsForm, setLimitsForm] = useState<Record<string, unknown>>({});
  const [agentDefaultsForm, setAgentDefaultsForm] = useState<Record<string, unknown>>({});
  const [orchestratorDefaultsForm, setOrchestratorDefaultsForm] = useState<Record<string, unknown>>({});

  // ─── Queries ───────────────────────────────────────────────────────

  const { data: modelsData, isLoading: modelsLoading } = useQuery<ModelListResponse>({
    queryKey: qk.admin.models.list({}),
    queryFn: () => adminApi.getModels({ size: 100 }),
  });
  const models: Model[] = modelsData?.items ?? [];

  // Platform settings
  const { data: platformSettings, isLoading: settingsLoading } = usePlatformSettings();
  const updateSettings = useUpdatePlatformSettings();
  const fillPlatformDefaults = useFillPlatformSettingsDefaults();

  const { data: platformLimits } = usePlatformExecutionLimits();
  const updatePlatformLimits = useUpdatePlatformExecutionLimits();
  const { data: agentDefaultLimits } = useAgentDefaultExecutionLimits();
  const updateAgentDefaultLimits = useUpdateAgentDefaultExecutionLimits();
  const { data: orchestratorDefaultLimits } = useOrchestratorDefaultExecutionLimits();
  const updateOrchestratorDefaultLimits = useUpdateOrchestratorDefaultExecutionLimits();

  // Credentials query
  const { data: credentials = [] } = useQuery({
    queryKey: qk.credentials.list({ owner_platform: true }),
    queryFn: () => credentialsApi.list({ owner_platform: true }),
  });

  // ─── Handlers ───────────────────────────────────────────────────────

  const handleEdit = () => {
    setFormData(platformSettings || {});
    setMode('edit');
  };

  const handleCancel = () => {
    setFormData({});
    setMode('view');
  };

  const handleSave = async () => {
    setPendingUpdates(formData);
    setShowConfirmDialog(true);
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleConfirmSave = () => {
    if (pendingUpdates) {
      updateSettings.mutate(pendingUpdates);
      setShowConfirmDialog(false);
      setPendingUpdates(null);
      setMode('view');
    }
  };

  const handleCancelSave = () => {
    setShowConfirmDialog(false);
    setPendingUpdates(null);
  };

  const fallbackTabActions = mode === 'view'
    ? [
        <Button
          key="fill-defaults"
          variant="outline"
          onClick={() => fillPlatformDefaults.mutate()}
          disabled={fillPlatformDefaults.isPending}
        >
          {fillPlatformDefaults.isPending ? 'Заполнение...' : 'Заполнить дефолтами'}
        </Button>,
        ...buildEntityCrudActions({
          mode,
          saving: updateSettings.isPending,
          tone: 'default',
          onEdit: handleEdit,
          onSave: handleSave,
          onCancel: handleCancel,
        }),
      ]
    : buildEntityCrudActions({
        mode,
        saving: updateSettings.isPending,
        tone: 'default',
        onEdit: handleEdit,
        onSave: handleSave,
        onCancel: handleCancel,
      });

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <>
      <EntityPageV2
        title="Настройки платформы"
        mode={mode}
      >
      <Tab
        title="Модели"
        layout="full"
        id="models"
        badge={models.length}
        actions={[
          <Button key="add-model" variant="primary" onClick={() => navigate('/admin/platform/models/new')}>
            {`${ADMIN_ACTION_LABELS.add} ${ADMIN_ENTITY_LABELS.model}`}
          </Button>,
        ]}
      >
        <DataTable
          columns={MODEL_FIELDS}
          data={models}
          keyField="id"
          loading={modelsLoading}
          emptyText="Модели не найдены."
          paginated
          pageSize={20}
          onRowClick={(m: Model) => navigate(`/admin/platform/models/${m.id}`)}
        />
      </Tab>

      {/* ── Tab 2: Ограничения — политики, gates, файлы ── */}
      <Tab
        title="Ограничения"
        layout="grid"
        id="restrictions"
        actions={buildEntityCrudActions({
          mode,
          saving: updateSettings.isPending,
          tone: 'default',
          onEdit: handleEdit,
          onSave: handleSave,
          onCancel: handleCancel,
        })}
      >
        <Block
          title="Политики (текст)"
          icon="file-text"
          iconVariant="primary"
          width="full"
          fields={POLICY_TEXT_FIELDS}
          data={mode === 'edit' ? formData : (platformSettings || {})}
          editable={mode === 'edit'}
          onChange={mode === 'edit' ? handleFieldChange : undefined}
        />
        
        <Block
          title="Policy Gates"
          icon="shield"
          iconVariant="primary"
          width="1/2"
          fields={POLICY_GATES_FIELDS}
          data={mode === 'edit' ? formData : (platformSettings || {})}
          editable={mode === 'edit'}
          onChange={mode === 'edit' ? handleFieldChange : undefined}
        />

        <Block
          title="Файлы чата"
          icon="upload"
          iconVariant="primary"
          width="1/2"
          fields={CHAT_UPLOAD_FIELDS}
          data={mode === 'edit' ? formData : (platformSettings || {})}
          editable={mode === 'edit'}
          onChange={mode === 'edit' ? handleFieldChange : undefined}
        />
      </Tab>

      {/* ── Tab 3: Фолбеки ── */}
      <Tab
        title="Фолбеки"
        layout="grid"
        id="fallbacks"
        actions={fallbackTabActions}
      >
        <Block
          title="Runtime правила"
          icon="clipboard-list"
          iconVariant="warning"
          width="2/3"
          fields={FALLBACK_RUNTIME_RULES_FIELDS}
          data={mode === 'edit' ? formData : (platformSettings || {})}
          editable={mode === 'edit'}
          onChange={mode === 'edit' ? handleFieldChange : undefined}
        />

        <Block
          title="Числовые фолбеки"
          icon="settings"
          iconVariant="success"
          width="1/3"
          fields={FALLBACK_NUMERIC_FIELDS}
          data={mode === 'edit' ? formData : (platformSettings || {})}
          editable={mode === 'edit'}
          onChange={mode === 'edit' ? handleFieldChange : undefined}
        />
      </Tab>

      {/* ── Tab 4: Runtime guards ── */}
      <Tab
        title="Лимиты runtime"
        layout="grid"
        id="limits"
        actions={
          limitsMode === 'view' ? [
            <Button key="edit" onClick={() => { setLimitsForm({ ...(platformLimits || {}) }); setLimitsMode('edit'); }}>{ADMIN_ACTION_LABELS.edit}</Button>,
          ] : [
            <Button
              key="save"
              onClick={async () => {
                await updatePlatformLimits.mutateAsync(
                  Object.fromEntries(RUN_LIMIT_FIELDS.map(field => [field.key, limitsForm[field.key]])),
                );
                setLimitsMode('view');
              }}
              disabled={updatePlatformLimits.isPending}
            >
              {updatePlatformLimits.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={() => setLimitsMode('view')}>Отмена</Button>,
          ]
        }
      >
        <Block
          title="Лимиты run"
          icon="settings"
          iconVariant="info"
          width="1/2"
          tooltip="Ограничения, общие для одного выполнения графа."
          fields={RUN_LIMIT_FIELDS}
          data={limitsMode === 'edit' ? limitsForm : { ...(platformLimits || {}) }}
          editable={limitsMode === 'edit'}
          onChange={limitsMode === 'edit' ? (k, v) => setLimitsForm(prev => ({ ...prev, [k]: v })) : undefined}
        />
      </Tab>

      <Tab
        title="Лимиты по умолчанию"
        layout="grid"
        id="default-limits"
        actions={[
          <Button key="save-defaults" onClick={async () => {
            await Promise.all([
              updateAgentDefaultLimits.mutateAsync(agentDefaultsForm),
              updateOrchestratorDefaultLimits.mutateAsync(orchestratorDefaultsForm),
            ]);
          }}>Сохранить</Button>,
        ]}
      >
        <Block title="Агенты" icon="bot" iconVariant="info" width="1/2" fields={AGENT_LIMIT_FIELDS}
          data={Object.keys(agentDefaultsForm).length ? agentDefaultsForm : (agentDefaultLimits?.effective || {})} editable
          onChange={(key, value) => setAgentDefaultsForm(prev => ({ ...(Object.keys(prev).length ? prev : (agentDefaultLimits?.effective || {})), [key]: value }))} />
        <Block title="Оркестраторы" icon="route" iconVariant="info" width="1/2" fields={ORCHESTRATOR_LIMIT_FIELDS}
          data={Object.keys(orchestratorDefaultsForm).length ? orchestratorDefaultsForm : (orchestratorDefaultLimits?.effective || {})} editable
          onChange={(key, value) => setOrchestratorDefaultsForm(prev => ({ ...(Object.keys(prev).length ? prev : (orchestratorDefaultLimits?.effective || {})), [key]: value }))} />
      </Tab>

      <Tab
        title="Общие доступы"
        layout="single"
        id="credentials"
        badge={credentials?.length || 0}
        actions={[
          <Button key="add-credential" variant="primary" onClick={() => navigate('/admin/credentials/new')}>
            {`${ADMIN_ACTION_LABELS.add} ${ADMIN_ENTITY_LABELS.access}`}
          </Button>,
        ]}
      >
        <CredentialsPanel mode="platform" />
      </Tab>

      <Tab
        title="RBAC"
        layout="full"
        id="rbac"
      >
        <RBACRulesTable mode="platform" />
      </Tab>
    </EntityPageV2>

    <ConfirmDialog
      open={showConfirmDialog}
      title="Подтвердите сохранение"
      message="Вы уверены, что хотите сохранить изменения в глобальных настройках платформы? Это повлияет на всех пользователей и агентов."
      confirmLabel={updateSettings.isPending ? 'Сохранение...' : 'Сохранить'}
      cancelLabel="Отмена"
      variant="warning"
      onConfirm={handleConfirmSave}
      onCancel={handleCancelSave}
    />
    </>
  );
}

export default PlatformSettingsPage;
