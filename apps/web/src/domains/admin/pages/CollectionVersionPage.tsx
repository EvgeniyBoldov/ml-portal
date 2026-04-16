import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  collectionsApi,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import {
  getVersionStatusPresentation,
  useVersionLifecycleActions,
} from '@/shared/hooks/useVersionLifecycleActions';
import { useCollectionVersionEditor } from '@/shared/api/hooks';

const PROFILE_FIELDS: FieldConfig[] = [
  {
    key: 'summary',
    type: 'textarea',
    label: 'Краткое описание',
    description: 'Одним абзацем: что это за коллекция и какую фактуру в ней искать.',
    placeholder: 'Регламенты эксплуатации и резервного копирования внутренних сервисов.',
    rows: 4,
  },
  {
    key: 'entity_types',
    type: 'tags',
    label: 'Типы сущностей',
    description: 'Короткие типы данных без пробелов. Нужны LLM, чтобы понять природу записей.',
    placeholder: 'document record incident',
  },
  {
    key: 'use_cases',
    type: 'textarea',
    label: 'Когда использовать',
    description: 'Какие запросы агент должен направлять в эту коллекцию.',
    placeholder: 'Когда нужно найти регламент, подтвердить расписание бэкапов или проверить внутреннюю инструкцию.',
    rows: 5,
  },
  {
    key: 'limitations',
    type: 'textarea',
    label: 'Ограничения',
    description: 'Что здесь неполно, ненадежно или чего тут точно нет.',
    placeholder: 'Не содержит фактический статус систем и не подходит для проверки live-состояния инфраструктуры.',
    rows: 5,
  },
  {
    key: 'examples',
    type: 'textarea',
    label: 'Примеры запросов',
    description: 'По одному примеру на строку. Это помогает LLM понять ожидаемые пользовательские вопросы.',
    placeholder: 'Во сколько выполняется инкрементальное резервное копирование?\nГде описан регламент восстановления PostgreSQL?',
    rows: 5,
  },
  {
    key: 'notes',
    type: 'textarea',
    label: 'Заметки к версии',
    description: 'Что изменилось именно в этой версии профайла.',
    placeholder: 'Уточнил ограничения и добавил примеры вопросов для поиска по регламентам.',
    rows: 3,
  },
];

const POLICY_FIELDS: FieldConfig[] = [
  {
    key: 'policy_dos',
    type: 'textarea',
    label: 'Что делать',
    description: 'По одному правилу на строку. Ожидаемое поведение агента при работе с коллекцией.',
    placeholder: 'Ссылайся на найденный документ по названию.\nУточняй период или систему, если запрос пользователя расплывчатый.',
    rows: 5,
  },
  {
    key: 'policy_donts',
    type: 'textarea',
    label: 'Чего не делать',
    description: 'Запреты и анти-паттерны при работе с данными коллекции.',
    placeholder: 'Не выдумывай регламент, если документ не найден.\nНе подменяй факт из документа общими знаниями модели.',
    rows: 5,
  },
  {
    key: 'policy_guardrails',
    type: 'textarea',
    label: 'Границы и проверки',
    description: 'Какие проверки и оговорки агент обязан делать перед выводом.',
    placeholder: 'Если найдено несколько похожих документов, покажи различия.\nЕсли данные устарели, явно скажи об этом в ответе.',
    rows: 5,
  },
  {
    key: 'policy_citation_rules',
    type: 'textarea',
    label: 'Правила цитирования',
    description: 'Как ссылаться на источник и какие детали нужно тащить в ответ.',
    placeholder: 'Указывай название документа и релевантный фрагмент.\nДля табличных данных указывай ключевые поля строки, по которым был сделан вывод.',
    rows: 5,
  },
  {
    key: 'policy_sensitive_fields',
    type: 'textarea',
    label: 'Чувствительные поля',
    description: 'По одному полю или категории на строку. Что нельзя раскрывать без отдельного решения.',
    placeholder: 'password\napi_key\npassport_data',
    rows: 4,
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'version', type: 'code', label: 'Версия', editable: false },
  { key: 'status', type: 'badge', label: 'Статус', badgeTone: 'neutral', editable: false },
  { key: 'is_primary', type: 'badge', label: 'Основная версия', badgeTone: 'info', editable: false },
  { key: 'created_at', type: 'date', label: 'Создана', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлена', editable: false },
];

export function CollectionVersionPage() {
  const { id, version: versionParam } = useParams<{ id: string; version: string }>();

  const {
    mode,
    isCreate,
    versionNumber,
    saving,
    isLoading: versionEditorLoading,
    parent: collection,
    existingVersion,
    formData,
    handleFieldChange,
    handleSave,
    handleCancel,
    activateMutation,
    deactivateMutation,
    setRecommendedMutation,
    onActivate,
    onDeactivate,
    onSetRecommended,
    onDuplicate,
  } = useCollectionVersionEditor(id!, versionParam);

  const { data: versions, isLoading: versionsLoading } = useQuery({
    queryKey: qk.collections.versions(id ?? ''),
    queryFn: () => collectionsApi.listVersions(id!),
    enabled: !!id,
  });

  const { data: collectionDetail, isLoading: collectionLoading } = useQuery({
    queryKey: qk.collections.detail(id ?? ''),
    queryFn: () => collectionsApi.getById(id!),
    enabled: !!id,
  });

  const nextVersionNumber = useMemo(() => {
    if (!isCreate) {
      return versionNumber ?? null;
    }
    const maxVersion = versions?.reduce((max, current) => Math.max(max, current.version), 0) ?? 0;
    return maxVersion + 1;
  }, [isCreate, versionNumber, versions]);
  const canEdit = isCreate || existingVersion?.status === 'draft';
  const isEditable = (mode === 'edit' || mode === 'create') && canEdit;
  const viewData = formData;
  const isPrimaryVersion = Boolean(
    !isCreate &&
    existingVersion?.id &&
    (collectionDetail?.current_version_id || collection?.current_version_id) === existingVersion.id,
  );

  const metaData = useMemo(() => ({
    version: isCreate ? `v${nextVersionNumber ?? ''}` : `v${existingVersion?.version ?? versionNumber ?? ''}`,
    status: getVersionStatusPresentation(existingVersion?.status).label,
    is_primary: isPrimaryVersion ? 'Да' : 'Нет',
    created_at: existingVersion?.created_at ?? '',
    updated_at: existingVersion?.updated_at ?? '',
  }), [existingVersion, isCreate, versionNumber, nextVersionNumber, isPrimaryVersion]);

  const breadcrumbs = [
    { label: 'Коллекции', href: '/admin/collections' },
    { label: collectionDetail?.name || collection?.name || id || '', href: `/admin/collections/${id}` },
    { label: isCreate ? `Версия ${nextVersionNumber ?? ''}` : `Версия ${versionNumber}` },
  ];

  const actionButtons = useVersionLifecycleActions({
    status: existingVersion?.status,
    isCreate,
    isPrimary: isPrimaryVersion,
    callbacks: {
      onPublish: onActivate,
      onSetPrimary: onSetRecommended,
      onArchive: onDeactivate,
      onClone: onDuplicate,
    },
    loading: {
      publish: activateMutation.isPending,
      primary: setRecommendedMutation.isPending,
      archive: deactivateMutation.isPending,
    },
  });

  return (
    <EntityPageV2
      title={`Версия ${nextVersionNumber ?? ''}${isCreate ? ' (новая)' : ''}`}
      mode={mode}
      breadcrumbs={breadcrumbs}
      loading={collectionLoading || versionsLoading || (!isCreate && versionEditorLoading)}
      saving={saving}
      backPath={`/admin/collections/${id}`}
      onSave={isEditable ? handleSave : undefined}
      onCancel={isEditable ? handleCancel : undefined}
      actionButtons={isEditable ? undefined : actionButtons}
    >
      <Tab title="Профайл" layout="grid" id="profile">
        <Block
          title="Профайл коллекции"
          icon="sparkles"
          iconVariant="info"
          width="2/3"
          fields={PROFILE_FIELDS}
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />
        <Block
          title="Информация о версии"
          icon="info"
          iconVariant="neutral"
          width="1/3"
          fields={META_FIELDS}
          data={metaData}
          editable={false}
        />
      </Tab>

      <Tab title="Policy Hints" layout="grid" id="policy">
        <Block
          title="Правила использования"
          icon="shield"
          iconVariant="warn"
          width="full"
          fields={POLICY_FIELDS}
          data={viewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default CollectionVersionPage;
