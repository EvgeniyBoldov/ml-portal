/**
 * PlatformSettingsPage - Global platform configuration (singleton)
 *
 * Tabs: Модели | Общие доступы | RBAC
 * Uses EntityPageV2 + Tab architecture.
 */
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { credentialsApi } from '@/shared/api/credentials';
import { adminApi, type Model, type ModelListResponse, type PlatformSettings, type PlatformSettingsUpdate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { DataTable, type DataTableColumn, Badge, Button } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { usePlatformSettings, useUpdatePlatformSettings, useOrchestrationSettings, useUpdateOrchestrationSettings } from '@/shared/api/hooks/usePlatformSettings';
import { useState } from 'react';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import {
  GLOBAL_CAPS_BLOCK_TITLE,
  GLOBAL_CAPS_TOOLTIP,
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

// Global Caps fields — hard platform ceiling, cannot be exceeded by any agent
const GLOBAL_CAPS_FIELDS: FieldConfig[] = [
  {
    key: 'abs_max_steps',
    type: 'number',
    label: 'Макс. шагов агента',
    description: 'Верхний предел шагов агентского цикла. Агент не может превысить это значение.',
    placeholder: '50',
  },
  {
    key: 'abs_max_timeout_s',
    type: 'number',
    label: 'Макс. таймаут (сек)',
    description: 'Верхний предел времени одного запуска агента в секундах.',
    placeholder: '300',
  },
  {
    key: 'abs_max_retries',
    type: 'number',
    label: 'Макс. ретраев',
    description: 'Верхний предел повторных попыток при ошибке инструмента.',
    placeholder: '10',
  },
  {
    key: 'abs_max_plan_steps',
    type: 'number',
    label: 'Макс. шагов планировщика',
    description: 'Верхний предел шагов внутри одного плана (planner loop).',
    placeholder: '20',
  },
  {
    key: 'abs_max_concurrency',
    type: 'number',
    label: 'Макс. параллельных запусков',
    description: 'Верхний предел одновременных запусков агента на один экземпляр.',
    placeholder: '10',
  },
  {
    key: 'abs_max_task_runtime_s',
    type: 'number',
    label: 'Макс. время задачи (сек)',
    description: 'Верхний предел суммарного времени выполнения задачи целиком.',
    placeholder: '3600',
  },
  {
    key: 'abs_max_tool_calls_per_step',
    type: 'number',
    label: 'Макс. вызовов инструментов за шаг',
    description: 'Верхний предел количества вызовов инструментов в рамках одного шага.',
    placeholder: '5',
  },
];

// Execution defaults — these apply when agent has no explicit override
const EXEC_DEFAULTS_FIELDS: FieldConfig[] = [
  {
    key: 'executor_max_steps',
    type: 'number',
    label: 'Макс. шагов (по умолч.)',
    description: 'Сколько итераций разрешено агенту, если он не задал свой лимит.',
    placeholder: '10',
  },
  {
    key: 'executor_timeout_s',
    type: 'number',
    label: 'Таймаут (сек, по умолч.)',
    description: 'Лимит времени одного запуска агента, если агент не задал свой таймаут.',
    placeholder: '60',
  },
  {
    key: 'executor_max_retries',
    type: 'number',
    label: 'Макс. попыток (по умолч.)',
    description: 'Сколько раз повторять вызов инструмента при ошибке, если агент не задал своё значение.',
    placeholder: '3',
  },
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

  // Limits tab — orchestration defaults (executor_max_steps/timeout_s/max_retries)
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

  // Orchestration defaults (limits tab)
  const { data: orchSettings } = useOrchestrationSettings();
  const updateOrchSettings = useUpdateOrchestrationSettings();

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
            + Добавить
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
        actions={
            mode === 'view' ? [
              <Button key="edit" onClick={handleEdit}>Редактировать</Button>,
            ] : mode === 'edit' ? [
              <Button 
                key="save" 
                onClick={handleSave} 
                disabled={updateSettings.isPending}
              >
                {updateSettings.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel}>Отмена</Button>,
            ] : []
          }
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

      {/* ── Tab 3: Лимиты — caps + exec defaults ── */}
      <Tab
        title="Лимиты"
        layout="grid"
        id="limits"
        actions={
          limitsMode === 'view' ? [
            <Button key="edit" onClick={() => { setLimitsForm({ ...(platformSettings || {}), ...(orchSettings || {}) }); setLimitsMode('edit'); }}>Редактировать</Button>,
          ] : [
            <Button
              key="save"
              onClick={() => {
                const capsKeys = GLOBAL_CAPS_FIELDS.map(f => f.key);
                const defaultsKeys = EXEC_DEFAULTS_FIELDS.map(f => f.key);
                const capsUpdate = Object.fromEntries(capsKeys.map(k => [k, limitsForm[k]]));
                const defaultsUpdate = Object.fromEntries(defaultsKeys.map(k => [k, limitsForm[k]]));
                updateSettings.mutate(capsUpdate as PlatformSettingsUpdate);
                updateOrchSettings.mutate(defaultsUpdate);
                setLimitsMode('view');
              }}
              disabled={updateSettings.isPending || updateOrchSettings.isPending}
            >
              {(updateSettings.isPending || updateOrchSettings.isPending) ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={() => setLimitsMode('view')}>Отмена</Button>,
          ]
        }
      >
        <Block
          title={GLOBAL_CAPS_BLOCK_TITLE}
          icon="zap"
          iconVariant="danger"
          width="1/2"
          tooltip={GLOBAL_CAPS_TOOLTIP}
          fields={GLOBAL_CAPS_FIELDS}
          data={limitsMode === 'edit' ? limitsForm : { ...(platformSettings || {}) }}
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
          data={limitsMode === 'edit' ? limitsForm : { ...(orchSettings || {}) }}
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
            + Добавить
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
