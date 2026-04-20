/**
 * ToolVersionPage — просмотр/создание/редактирование версии релиза инструмента.
 *
 * После удаления semantic/policy слоя в релизе управляется только backend release.
 */
import { useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  toolReleasesApi,
  toolReleasesKeys,
  type ToolDetail,
  type ToolReleaseResponse,
  type ToolReleaseCreate,
} from '@/shared/api/toolReleases';
import { qk } from '@/shared/api/keys';
import { useVersionEditor } from '@/shared/hooks/useVersionEditor';
import { getVersionStatusPresentation, useVersionLifecycleActions } from '@/shared/hooks/useVersionLifecycleActions';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import {
  TOOL_BACKEND_RELEASE_INFO_FIELDS,
  TOOL_META_FIELDS,
  buildToolReleasePayload,
  buildToolReleaseVersionData,
} from '../shared/toolFields';

type ToolReleaseFormData = {
  backend_release_id: string | null;
};

function buildBackendReleaseField(options: Array<{ value: string; label: string }>): FieldConfig {
  return {
    key: 'backend_release_id',
    type: 'select',
    label: 'Backend release',
    options,
    placeholder: 'Выберите backend release',
  };
}

function toBackendReleaseOptions(tool: ToolDetail | undefined) {
  return (tool?.backend_releases ?? []).map((release) => ({
    value: release.id,
    label: `${release.version}${release.deprecated ? ' (deprecated)' : ''}`,
  }));
}

export function ToolVersionPage() {
  const { id, version: versionParam } = useParams<{ id: string; version: string }>();
  const [searchParams] = useSearchParams();
  const fromVersionParam = searchParams.get('from');

  const {
    mode,
    isCreate,
    versionNumber,
    formData,
    saving,
    isLoading,
    parent: tool,
    existingVersion: version,
    activateMutation,
    deactivateMutation,
    setRecommendedMutation,
    handleFieldChange,
    handleSave,
    handleCancel,
    onActivate,
    onDeactivate,
    onSetRecommended,
    onDuplicate,
  } = useVersionEditor<ToolDetail, ToolReleaseResponse, ToolReleaseFormData, ToolReleaseCreate>({
    slug: id!,
    versionParam,
    fromVersionParam,
    queryKeys: {
      parentDetail: (slug) => qk.tools.detail(slug),
      versionsList: (slug) => toolReleasesKeys.releases(slug),
      versionDetail: (slug, version) => toolReleasesKeys.releaseDetail(slug, version),
    },
    api: {
      getParent: (slug) => toolReleasesApi.getTool(slug),
      getVersion: (slug, version) => toolReleasesApi.getRelease(slug, version),
      createVersion: (slug, data) => toolReleasesApi.createRelease(slug, data),
      updateVersion: (slug, version, data) => toolReleasesApi.updateRelease(slug, version, data),
      activateVersion: (slug, version) => toolReleasesApi.activateRelease(slug, version),
      deactivateVersion: (slug, version) => toolReleasesApi.archiveRelease(slug, version),
      setRecommendedVersion: toolReleasesApi.setCurrentVersion,
      deleteVersion: (slug, version) => toolReleasesApi.deleteRelease(slug, version),
    },
    getInitialFormData: (v) => {
      const data = buildToolReleaseVersionData(v);
      return {
        backend_release_id: data?.backend_release_id ? String(data.backend_release_id) : null,
      };
    },
    buildCreatePayload: (fd, sourceVersion) => ({
      ...(buildToolReleasePayload(fd as Record<string, unknown>) as ToolReleaseCreate),
      from_release_id: sourceVersion?.id,
    }),
    basePath: '/admin/tools',
    messages: {
      created: 'Версия инструмента создана',
      updated: 'Версия инструмента обновлена',
      published: 'Версия опубликована',
      archived: 'Версия архивирована',
      deleted: 'Версия удалена',
    },
  });

  const backendReleaseOptions = toBackendReleaseOptions(tool);
  const backendReleaseSelectField = buildBackendReleaseField(backendReleaseOptions);

  useEffect(() => {
    if (isCreate && backendReleaseOptions.length > 0 && !formData.backend_release_id) {
      handleFieldChange('backend_release_id', backendReleaseOptions[0].value);
    }
  }, [backendReleaseOptions, formData.backend_release_id, handleFieldChange, isCreate]);

  const canEdit = isCreate || version?.status === 'draft';
  const isEditable = (mode === 'edit' || mode === 'create') && canEdit;

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: tool?.name || id || '', href: `/admin/tools/${id}` },
    { label: isCreate ? 'Новая версия релиза' : `Версия релиза ${versionNumber}` },
  ];

  const isPrimary = Boolean(tool?.current_version?.id && version?.id && tool.current_version.id === version.id);
  const statusPresentation = getVersionStatusPresentation(version?.status);

  const viewData = isEditable
    ? formData
    : buildToolReleaseVersionData(version) ?? {
        backend_release_id: null,
      };

  const metaData = {
    version: versionNumber,
    status: statusPresentation.label,
    is_primary: isPrimary ? 'Да' : 'Нет',
    created_at: version?.created_at ?? '',
    updated_at: version?.updated_at ?? '',
  };

  const backendViewData = isEditable
    ? { backend_release_id: formData.backend_release_id ?? null }
    : {
        version: version?.backend_release?.version ?? '—',
        method_name: version?.backend_release?.method_name ?? '—',
        description: version?.backend_release?.description ?? '—',
        worker_build_id: version?.backend_release?.worker_build_id ?? '—',
      };

  const actionButtons = useVersionLifecycleActions({
    status: version?.status,
    isCreate,
    isPrimary,
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
      title={isCreate ? 'Новая версия релиза' : `Версия релиза ${versionNumber}`}
      mode={mode}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      backPath={`/admin/tools/${id || ''}`}
      onSave={isEditable ? handleSave : undefined}
      onCancel={isEditable ? handleCancel : undefined}
      actionButtons={isEditable ? undefined : actionButtons}
    >
      <Tab title="Основное" layout="grid" id="general">
        <Block
          title="Deprecated"
          icon="alert-triangle"
          iconVariant="warn"
          width="full"
        >
          Экран versioning для tool-container помечен deprecated и оставлен только для обратной совместимости.
        </Block>
        <Block
          title="Версия релиза"
          icon="info"
          iconVariant="info"
          width="1/2"
          fields={TOOL_META_FIELDS}
          data={metaData}
          editable={false}
        />
        <Block
          title="Backend release"
          icon="database"
          iconVariant="primary"
          width="1/2"
          fields={isEditable ? [backendReleaseSelectField] : backendViewData.version ? TOOL_BACKEND_RELEASE_INFO_FIELDS : []}
          data={backendViewData}
          editable={isEditable}
          onChange={handleFieldChange}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default ToolVersionPage;
