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

const DETAILS_FIELDS: FieldConfig[] = [
  {
    key: 'notes',
    type: 'textarea',
    label: 'Заметки к версии',
    description: 'Произвольные заметки для команды о том, что изменилось в версии.',
    placeholder: 'Например: обновили описание коллекции и entity_type на карточке коллекции.',
    rows: 6,
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
      <Tab title="Версия" layout="grid" id="version">
        <Block
          title="Сведения"
          icon="file-text"
          iconVariant="info"
          width="2/3"
          fields={DETAILS_FIELDS}
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
    </EntityPageV2>
  );
}

export default CollectionVersionPage;
