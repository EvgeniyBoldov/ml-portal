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
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { usePlatformSettings, useUpdatePlatformSettings, useFillPlatformSettingsDefaults, usePlatformExecutionLimits, useUpdatePlatformExecutionLimits } from '@/shared/api/hooks/usePlatformSettings';
import { useState } from 'react';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import {
  EXEC_DEFAULTS_BLOCK_TITLE,
  EXEC_DEFAULTS_TOOLTIP,
} from './platformLimitsTooltips';

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
    description: 'Используется, если execution limits не задали runtime_steps_max.',
  },
  {
    key: 'synth_chunk_size',
    type: 'number',
    label: 'Размер синтез-чанка',
    description: 'Размер чанка для synth delta streaming в short-circuit/fallback путях.',
    min: 1,
  },
];

const LLM_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'llm_input_tokens_max', type: 'number', label: 'LLM input токены', description: 'Лимит токенов входного промпта для одного LLM-вызова.' },
  { key: 'llm_output_tokens_max', type: 'number', label: 'LLM output токены', description: 'Лимит токенов ответа для одного LLM-вызова.' },
  { key: 'llm_context_window_max', type: 'number', label: 'LLM context window', description: 'Лимит input+output токенов в одном LLM-вызове.' },
];

const EXEC_DEFAULTS_FIELDS: FieldConfig[] = [
  { key: 'runtime_steps_max', type: 'number', label: 'Runtime шаги', description: 'Лимит шагов рантайма.' },
  { key: 'runtime_tool_calls_max', type: 'number', label: 'Runtime вызовы инструментов', description: 'Лимит числа tool-вызовов за ран.' },
  { key: 'runtime_retries_max', type: 'number', label: 'Runtime ретраи', description: 'Лимит повторных попыток.' },
  { key: 'runtime_wall_time_ms_max', type: 'number', label: 'Runtime wall time (ms)', description: 'Лимит общего времени выполнения в мс.' },
  { key: 'runtime_tokens_total_max', type: 'number', label: 'Runtime total токены', description: 'Лимит суммарных токенов рантайма.' },
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
          variant="secondary"
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

      {/* ── Tab 4: Лимиты платформы (execution_limits) ── */}
      <Tab
        title="Лимиты"
        layout="grid"
        id="limits"
        actions={
          limitsMode === 'view' ? [
            <Button key="edit" onClick={() => { setLimitsForm({ ...(platformSettings || {}), ...(platformLimits || {}) }); setLimitsMode('edit'); }}>{ADMIN_ACTION_LABELS.edit}</Button>,
          ] : [
            <Button
              key="save"
              onClick={async () => {
                const llmKeys = LLM_LIMIT_FIELDS.map(f => f.key);
                const defaultsKeys = EXEC_DEFAULTS_FIELDS.map(f => f.key);
                const llmUpdate = Object.fromEntries(llmKeys.map(k => [k, limitsForm[k]]));
                const defaultsUpdate = Object.fromEntries(defaultsKeys.map(k => [k, limitsForm[k]]));
                await updatePlatformLimits.mutateAsync(llmUpdate);
                await updatePlatformLimits.mutateAsync(defaultsUpdate);
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
          title="Лимиты LLM"
          icon="zap"
          iconVariant="warning"
          width="1/2"
          fields={LLM_LIMIT_FIELDS}
          data={limitsMode === 'edit' ? limitsForm : { ...(platformLimits || {}) }}
          editable={limitsMode === 'edit'}
          onChange={limitsMode === 'edit' ? (k, v) => setLimitsForm(prev => ({ ...prev, [k]: v })) : undefined}
        />

        <Block
          title={EXEC_DEFAULTS_BLOCK_TITLE}
          icon="settings"
          iconVariant="info"
          width="1/2"
          tooltip={EXEC_DEFAULTS_TOOLTIP}
          fields={EXEC_DEFAULTS_FIELDS}
          data={limitsMode === 'edit' ? limitsForm : { ...(platformLimits || {}) }}
          editable={limitsMode === 'edit'}
          onChange={limitsMode === 'edit' ? (k, v) => setLimitsForm(prev => ({ ...prev, [k]: v })) : undefined}
        />
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
