/**
 * AgentVersionPage - Admin page for managing Agent Versions
 *
 * Tabs:
 * 1. Промпт — prompt parts (identity, mission, scope, rules, tool_use_rules, output_format, examples)
 * 2. Выполнение — safety knobs + заметки
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  EntityPageV2,
  Tab,
  type BreadcrumbItem,
} from '@/shared/ui';
import { AIGenerateButton } from '@/shared/ui/AIGenerateButton';
import { ContractAwareEditor } from '@/shared/ui/ContractAwareEditor/ContractAwareEditor';
import {
  Block,
  type FieldConfig,
} from '@/shared/ui/GridLayout';
import { getVersionStatusPresentation, useVersionLifecycleActions } from '@/shared/hooks/useVersionLifecycleActions';
import { useAgentVersionEditor } from '@/shared/api/hooks';
import { Textarea, ConfirmDialog } from '@/shared/ui';

/* ─── Field configs ─── */

const IDENTITY_FIELDS: FieldConfig[] = [
  {
    key: 'identity',
    type: 'custom',
    label: 'Identity',
    description: 'Кто по жизни',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Identity"
        disabled={!editable}
        rows={4}
        placeholder="Ты — опытный сетевой инженер..."
      />
    ),
  },
  {
    key: 'mission',
    type: 'custom',
    label: 'Mission',
    description: 'Предназначение агента',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Mission"
        disabled={!editable}
        rows={4}
        placeholder="Помогаешь диагностировать и решать сетевые проблемы..."
      />
    ),
  },
  {
    key: 'scope',
    type: 'custom',
    label: 'Scope',
    description: 'Границы (что делает / что НЕ делает)',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Scope"
        disabled={!editable}
        rows={4}
        placeholder="Работаешь только с сетевым оборудованием. НЕ занимаешься серверами..."
      />
    ),
  },
  {
    key: 'planner_short_info',
    type: 'custom',
    label: 'Short Info (Planner)',
    description: 'Используется только планером для выбора агента; в системный промпт агента не входит',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Short Info (Planner)"
        disabled={!editable}
        rows={3}
        placeholder="Коротко: когда этот агент должен вызываться планером"
      />
    ),
  },
];

const RULES_FIELDS: FieldConfig[] = [
  {
    key: 'rules',
    type: 'custom',
    label: 'Rules',
    description: 'Алгоритм/гайдлайны',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Rules"
        disabled={!editable}
        rows={6}
        placeholder="1. Сначала уточни hostname или IP..."
      />
    ),
  },
  {
    key: 'tool_use_rules',
    type: 'custom',
    label: 'Tool Use Rules',
    description: 'Когда/как вызывать инструменты',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Tool Use Rules"
        disabled={!editable}
        rows={6}
        placeholder="Всегда вызывай netbox_search перед изменениями..."
      />
    ),
  },
];

const OUTPUT_FIELDS: FieldConfig[] = [
  {
    key: 'output_format',
    type: 'custom',
    label: 'Output Format',
    description: 'Структура ответа',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Output Format"
        disabled={!editable}
        rows={5}
        placeholder={'Отвечай в формате:\n## Диагноз\n## Шаги\n## Результат'}
      />
    ),
  },
  {
    key: 'examples',
    type: 'custom',
    label: 'Examples',
    description: 'Few-shot примеры ответов',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Examples"
        disabled={!editable}
        rows={5}
        placeholder={'User: проверь статус свитча...\nAssistant: ...'}
      />
    ),
  },
];


const SAFETY_FIELDS: FieldConfig[] = [
  {
    key: 'never_do',
    type: 'custom',
    label: 'Never Do',
    description: 'Что запрещено делать агенту',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Never Do"
        disabled={!editable}
        rows={3}
        placeholder="Никогда не удаляй данные без подтверждения..."
      />
    ),
  },
  {
    key: 'allowed_ops',
    type: 'custom',
    label: 'Allowed Ops',
    description: 'Что можно делать',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Allowed Ops"
        disabled={!editable}
        rows={3}
        placeholder="read, search, create_ticket..."
      />
    ),
  },
  {
    key: 'supports_dynamic_contracts',
    type: 'boolean',
    label: 'Разрешить динамические контракты',
    description: 'Разрешает компилятору принимать проверенные динамические контракты задач.',
  },
  {
    key: 'requires_fresh_retrieval',
    type: 'boolean',
    label: 'Требовать свежий поиск',
    description: 'Каждая задача должна получать свежие данные через инструменты.',
  },
  {
    key: 'task_contracts_json',
    type: 'custom',
    label: 'Task contracts (JSON)',
    description: 'Массив опубликованных именованных контрактов задач.',
    render: (value, editable, onChange) => (
      <Textarea
        id="agent-task-contracts-json"
        aria-label="Task contracts (JSON)"
        rows={10}
        value={String(value ?? '[]')}
        disabled={!editable}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false}
      />
    ),
  },
];

const NOTES_FIELDS: FieldConfig[] = [
  {
    key: 'notes',
    type: 'custom',
    label: 'Заметки к версии',
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={onChange}
        fieldLabel="Заметки к версии"
        disabled={!editable}
        rows={3}
        placeholder="Описание изменений в этой версии..."
      />
    ),
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'version', type: 'code', label: 'Версия', editable: false },
  { key: 'status', type: 'badge', label: 'Статус', badgeTone: 'neutral', editable: false },
  { key: 'is_primary', type: 'badge', label: 'Основная версия', badgeTone: 'info', editable: false },
  { key: 'created_at', type: 'date', label: 'Создана', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлена', editable: false },
];

/* ─── Component ─── */

export function AgentVersionPage() {
  const { id, version: versionParam } = useParams<{ id: string; version: string }>();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const {
    mode, isCreate, versionNumber, saving, isLoading,
    parent: agent, existingVersion,
    formData, handleFieldChange, handleSave, handleEdit, handleCancel,
    activateMutation: publishMutation,
    deactivateMutation: archiveMutation,
    setRecommendedMutation,
    deleteMutation,
    onActivate: onPublish,
    onDeactivate: onArchive,
    onSetRecommended,
    onDuplicate,
  } = useAgentVersionEditor(id!, versionParam);

  const isDraft = existingVersion?.status === 'draft';
  const canEdit = isCreate || isDraft;
  const isEditable = (mode === 'edit' || mode === 'create') && canEdit;

  // ─── AI Generation ───
  const availableFields = [
    { key: 'identity', label: 'Identity', description: 'Кем является агент' },
    { key: 'mission', label: 'Mission', description: 'Основная задача агента' },
    { key: 'scope', label: 'Scope', description: 'Границы возможностей' },
    { key: 'rules', label: 'Rules', description: 'Правила поведения' },
    { key: 'tool_use_rules', label: 'Tool Use Rules', description: 'Правила использования инструментов' },
    { key: 'output_format', label: 'Output Format', description: 'Формат вывода' },
    { key: 'examples', label: 'Examples', description: 'Примеры использования' },
    { key: 'tags', label: 'Tags', description: 'Теги для категоризации' },
  ];

  const handleAIGenerate = (filledFields: Record<string, unknown>) => {
    // Заполнить форму сгенерированными данными
    Object.entries(filledFields).forEach(([field, value]) => {
      handleFieldChange(field, value);
    });
  };

  const isPrimary = Boolean(agent?.current_version_id && existingVersion?.id && agent.current_version_id === existingVersion.id);

  // ─── Derived data ───
  const viewData = mode === 'edit' || mode === 'create' ? formData : {
    identity: existingVersion?.identity ?? '',
    mission: existingVersion?.mission ?? '',
    scope: existingVersion?.scope ?? '',
    planner_short_info: existingVersion?.planner_short_info ?? '',
    rules: existingVersion?.rules ?? '',
    tool_use_rules: existingVersion?.tool_use_rules ?? '',
    output_format: existingVersion?.output_format ?? '',
    examples: existingVersion?.examples ?? '',
    never_do: existingVersion?.never_do ?? '',
    allowed_ops: existingVersion?.allowed_ops ?? '',
    tags: existingVersion?.tags ?? [],
    task_contracts_json: JSON.stringify(existingVersion?.task_contracts ?? [], null, 2),
    supports_dynamic_contracts: existingVersion?.supports_dynamic_contracts ?? true,
    requires_fresh_retrieval: existingVersion?.requires_fresh_retrieval ?? false,
    notes: existingVersion?.notes ?? '',
  };

  const metaData = {
    version: versionNumber,
    status: getVersionStatusPresentation(existingVersion?.status).label,
    is_primary: isPrimary ? 'Да' : 'Нет',
    created_at: existingVersion?.created_at ?? '',
    updated_at: existingVersion?.updated_at ?? '',
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Агенты', href: '/admin/agents' },
    { label: agent?.name || id || '', href: `/admin/agents/${id}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const actionButtons = useVersionLifecycleActions({
    status: existingVersion?.status,
    isCreate,
    isPrimary,
    callbacks: {
      onEdit: handleEdit,
      onPublish,
      onSetPrimary: onSetRecommended,
      onArchive,
      onClone: onDuplicate,
      onDelete: () => setShowDeleteConfirm(true),
    },
    loading: { 
      publish: publishMutation.isPending,
      primary: setRecommendedMutation.isPending,
      archive: archiveMutation.isPending,
      delete: deleteMutation.isPending,
    },
  });

  // ─── Render ───
  return (
    <>
    <EntityPageV2
      title={isCreate ? 'Новая версия' : `Версия ${versionNumber}`}
      mode={mode}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      backPath={`/admin/agents/${id}`}
      onSave={isEditable ? handleSave : undefined}
      onCancel={isEditable ? handleCancel : undefined}
      actionButtons={isEditable ? undefined : actionButtons}
    >
      {/* ── Tab 1: Промпт ── */}
      <Tab title="Промпт" layout="grid" id="prompt">
        <Block
          title="Identity & Mission"
          icon="user"
          iconVariant="info"
          width="1/2"
          fields={IDENTITY_FIELDS}
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
          headerActions={
            isEditable ? (
              <AIGenerateButton
                entityType="agent"
                entityId={id!}
                description={agent?.description || ''}
                availableFields={availableFields}
                onFieldsFilled={handleAIGenerate}
                context={{ agent_name: agent?.name }}
                disabled={!agent?.description}
                size="sm"
              />
            ) : undefined
          }
        />

        <Block
          title="Rules & Tool Use"
          icon="list"
          iconVariant="primary"
          width="1/2"
          fields={RULES_FIELDS}
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />

        <Block
          title="Output Format & Examples"
          icon="file-text"
          iconVariant="neutral"
          width="full"
          fields={OUTPUT_FIELDS}
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />
      </Tab>

      {/* ── Tab 2: Выполнение ── */}
      <Tab title="Выполнение" layout="grid" id="execution">
        <Block
          title="Safety Knobs"
          icon="shield"
          iconVariant="warn"
          width="1/2"
          fields={SAFETY_FIELDS}
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />

        <Block
          title="Заметки & Метаданные"
          icon="database"
          iconVariant="neutral"
          width="1/2"
          fields={[...NOTES_FIELDS, ...META_FIELDS]}
          data={{ ...viewData, ...metaData }}
          editable={isEditable}
          onChange={handleFieldChange}
        />
      </Tab>

    </EntityPageV2>
    <ConfirmDialog
      open={showDeleteConfirm}
      title="Удалить версию?"
      message={`Версия ${versionNumber} будет удалена без возможности восстановления.`}
      confirmLabel="Удалить"
      cancelLabel="Отмена"
      confirmLoading={deleteMutation.isPending}
      onCancel={() => setShowDeleteConfirm(false)}
      onConfirm={() => deleteMutation.mutate()}
    />
    </>
  );
}

export default AgentVersionPage;
