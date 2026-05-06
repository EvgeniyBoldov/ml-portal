/**
 * AgentVersionPage - Admin page for managing Agent Versions
 *
 * Tabs:
 * 1. Промпт — prompt parts (identity, mission, scope, rules, tool_use_rules, output_format, examples)
 * 2. Выполнение — safety knobs + заметки
 * 3. Роутинг — routing config
 */
import { useParams } from 'react-router-dom';
import {
  EntityPageV2,
  Tab,
  type BreadcrumbItem,
} from '@/shared/ui';
import { AIGenerateButton } from '@/shared/ui/AIGenerateButton';
import {
  Block,
  type FieldConfig,
} from '@/shared/ui/GridLayout';
import { getVersionStatusPresentation, useVersionLifecycleActions } from '@/shared/hooks/useVersionLifecycleActions';
import { useAgentVersionEditor } from '@/shared/api/hooks';

/* ─── Field configs ─── */

const IDENTITY_FIELDS: FieldConfig[] = [
  {
    key: 'identity',
    type: 'textarea',
    label: 'Identity',
    description: 'Кто по жизни',
    placeholder: 'Ты — опытный сетевой инженер...',
    rows: 4,
  },
  {
    key: 'mission',
    type: 'textarea',
    label: 'Mission',
    description: 'Предназначение агента',
    placeholder: 'Помогаешь диагностировать и решать сетевые проблемы...',
    rows: 4,
  },
  {
    key: 'scope',
    type: 'textarea',
    label: 'Scope',
    description: 'Границы (что делает / что НЕ делает)',
    placeholder: 'Работаешь только с сетевым оборудованием. НЕ занимаешься серверами...',
    rows: 4,
  },
];

const RULES_FIELDS: FieldConfig[] = [
  {
    key: 'rules',
    type: 'textarea',
    label: 'Rules',
    description: 'Алгоритм/гайдлайны',
    placeholder: '1. Сначала уточни hostname или IP...',
    rows: 6,
  },
  {
    key: 'tool_use_rules',
    type: 'textarea',
    label: 'Tool Use Rules',
    description: 'Когда/как вызывать инструменты',
    placeholder: 'Всегда вызывай netbox_search перед изменениями...',
    rows: 6,
  },
];

const OUTPUT_FIELDS: FieldConfig[] = [
  {
    key: 'output_format',
    type: 'textarea',
    label: 'Output Format',
    description: 'Структура ответа',
    placeholder: 'Отвечай в формате:\n## Диагноз\n## Шаги\n## Результат',
    rows: 5,
  },
  {
    key: 'examples',
    type: 'textarea',
    label: 'Examples',
    description: 'Few-shot примеры ответов',
    placeholder: 'User: проверь статус свитча...\nAssistant: ...',
    rows: 5,
  },
];


const SAFETY_FIELDS: FieldConfig[] = [
  {
    key: 'requires_confirmation_for_write',
    type: 'boolean',
    label: 'Write',
    description: 'Требует подтверждения для write-операций',
  },
  {
    key: 'risk_level',
    type: 'select',
    label: 'Уровень риска',
    options: [
      { value: 'low', label: 'Low' },
      { value: 'medium', label: 'Medium' },
      { value: 'high', label: 'High' },
      { value: 'destructive', label: 'Destructive' },
    ],
  },
  {
    key: 'never_do',
    type: 'textarea',
    label: 'Never Do',
    description: 'Что запрещено делать агенту',
    placeholder: 'Никогда не удаляй данные без подтверждения...',
    rows: 3,
  },
  {
    key: 'allowed_ops',
    type: 'textarea',
    label: 'Allowed Ops',
    description: 'Что можно делать',
    placeholder: 'read, search, create_ticket...',
    rows: 3,
  },
];

const ROUTING_FIELDS: FieldConfig[] = [
  {
    key: 'short_info',
    type: 'textarea',
    label: 'Short Info',
    description: 'Краткое описание для роутера',
    placeholder: 'Одна фраза — что делает агент и когда его вызывать...',
    rows: 2,
  },
  {
    key: 'tags',
    type: 'tags',
    label: 'Теги',
    description: 'Теги для роутинга и фильтрации',
    placeholder: 'network security monitoring...',
  },
  {
    key: 'is_routable',
    type: 'boolean',
    label: 'Доступен для авто-роутинга',
    description: 'Может ли агент быть автоматически выбран роутером',
  },
  {
    key: 'routing_keywords',
    type: 'tags',
    label: 'Ключевые слова',
    description: 'Слова для поиска (5-30)',
    placeholder: 'тикет инцидент алерт падение...',
  },
  {
    key: 'routing_negative_keywords',
    type: 'tags',
    label: 'Стоп-слова',
    description: 'Слова которые должны исключить выбор агента',
    placeholder: 'продажи маркетинг аналитика...',
  },
];

const NOTES_FIELDS: FieldConfig[] = [
  {
    key: 'notes',
    type: 'textarea',
    label: 'Заметки к версии',
    placeholder: 'Описание изменений в этой версии...',
    rows: 3,
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

  const {
    mode, isCreate, versionNumber, saving, isLoading,
    parent: agent, existingVersion,
    formData, handleFieldChange, handleSave, handleEdit, handleCancel,
    activateMutation: publishMutation,
    deactivateMutation: archiveMutation,
    setRecommendedMutation,
    onActivate: onPublish,
    onDeactivate: onArchive,
    onSetRecommended,
    onDuplicate,
  } = useAgentVersionEditor(id!, versionParam);

  const isDraft = existingVersion?.status === 'draft';
  const canEdit = isCreate || isDraft;
  const isEditable = (mode === 'edit' || mode === 'create') && canEdit;
  const showDraftBadge = isEditable && isDraft;

  // ─── AI Generation ───
  const availableFields = [
    { key: 'identity', label: 'Identity', description: 'Кем является агент' },
    { key: 'mission', label: 'Mission', description: 'Основная задача агента' },
    { key: 'scope', label: 'Scope', description: 'Границы возможностей' },
    { key: 'rules', label: 'Rules', description: 'Правила поведения' },
    { key: 'tool_use_rules', label: 'Tool Use Rules', description: 'Правила использования инструментов' },
    { key: 'output_format', label: 'Output Format', description: 'Формат вывода' },
    { key: 'examples', label: 'Examples', description: 'Примеры использования' },
    { key: 'short_info', label: 'Short Info', description: 'Краткое описание' },
    { key: 'tags', label: 'Tags', description: 'Теги для категоризации' },
  ];

  const handleAIGenerate = (filledFields: Record<string, any>) => {
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
    rules: existingVersion?.rules ?? '',
    tool_use_rules: existingVersion?.tool_use_rules ?? '',
    output_format: existingVersion?.output_format ?? '',
    examples: existingVersion?.examples ?? '',
    requires_confirmation_for_write: existingVersion?.requires_confirmation_for_write ?? false,
    risk_level: existingVersion?.risk_level ?? '',
    never_do: existingVersion?.never_do ?? '',
    allowed_ops: existingVersion?.allowed_ops ?? '',
    // Routing
    short_info: existingVersion?.short_info ?? '',
    tags: existingVersion?.tags ?? [],
    is_routable: existingVersion?.is_routable ?? false,
    routing_keywords: existingVersion?.routing_keywords ?? [],
    routing_negative_keywords: existingVersion?.routing_negative_keywords ?? [],
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
    },
    loading: { 
      publish: publishMutation.isPending,
      primary: setRecommendedMutation.isPending,
      archive: archiveMutation.isPending,
    },
  });

  // ─── Render ───
  return (
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
      headerActions={
        showDraftBadge ? (
          <span style={{
            fontSize: 12,
            fontWeight: 600,
            padding: '3px 10px',
            borderRadius: 6,
            background: 'var(--warning-muted, #fef3c7)',
            color: 'var(--warning, #d97706)',
            border: '1px solid var(--warning-border, #fde68a)',
          }}>
            Редактирование черновика
          </span>
        ) : undefined
      }
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

      {/* ── Tab 3: Роутинг ── */}
      <Tab title="Роутинг" layout="grid" id="routing">
        <Block
          title="Настройки роутинга"
          icon="route"
          iconVariant="primary"
          width="1/2"
          fields={ROUTING_FIELDS.slice(0, 3)} // short_info, tags, is_routable
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />

        <Block
          title="Ключевые слова"
          icon="search"
          iconVariant="info"
          width="1/2"
          fields={ROUTING_FIELDS.slice(3)} // routing_keywords, routing_negative_keywords
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />
      </Tab>

    </EntityPageV2>
  );
}

export default AgentVersionPage;
