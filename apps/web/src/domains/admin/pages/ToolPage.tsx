/**
 * ToolPage — tool release page.
 *
 * Shows the backend tool registry record, active release version, schema releases and release version history.
 * Version editing stays on ToolVersionPage.
 */
import { useParams } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { useToolDetail } from '@/shared/api/hooks';
import { toolReleasesApi } from '@/shared/api/toolReleases';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui';
import { Block } from '@/shared/ui/GridLayout';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import {
  TOOL_INFO_FIELDS,
  TOOL_META_FIELDS,
  TOOL_BACKEND_RELEASE_INFO_FIELDS,
  TOOL_BACKEND_RELEASE_META_FIELDS,
  TOOL_VERSION_POLICY_FIELDS,
  TOOL_VERSION_PROFILE_FIELDS,
  TOOL_STATS_FIELDS,
  buildToolReleaseVersionData,
  buildJsonFieldConfig,
  buildToolVersionMetaData,
  buildToolBackendReleaseInfoData,
  buildToolBackendReleaseMetaData,
} from '../shared/toolFields';

export function ToolPage() {
  const { id } = useParams<{ id: string }>();

  const {
    entity: tool,
    isLoading,
  } = useToolDetail(id!);

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: tool?.name || id || '' },
  ];

  const versionInfo =
    tool?.releases?.map((v) => ({
      id: v.id,
      version: v.version,
      status: v.status,
      created_at: v.created_at,
    })) || [];

  const toolData = tool ? {
    name: tool.name ?? '',
    domains: tool.domains ?? [],
    tags: tool.tags ?? [],
  } : {};
  const statsData = {
    releases_count: tool?.releases?.length || 0,
    backend_releases_count: tool?.backend_releases?.length || 0,
    has_current_version: tool?.current_version ? 'Да' : 'Нет',
  };
  const versionMetaData = tool ? buildToolVersionMetaData(tool) : {};
  const activeVersionData = buildToolReleaseVersionData(tool?.current_version);
  const hasRelease = !!activeVersionData;
  const backendReleaseDetails = useQueries({
    queries: (tool?.backend_releases ?? []).map((release) => ({
      queryKey: ['tools', 'backend-release', id, release.version],
      queryFn: () => toolReleasesApi.getBackendRelease(id!, release.version),
      enabled: !!id,
    })),
  });

  if (isLoading) {
    return (
      <EntityPageV2 title="Загрузка..." mode="view" breadcrumbs={breadcrumbs} loading>
        <></>
      </EntityPageV2>
    );
  }

  if (!tool) {
    return (
      <EntityPageV2 title="Не найдено" mode="view" breadcrumbs={breadcrumbs} loading={false}>
        <></>
      </EntityPageV2>
    );
  }

  return (
    <EntityPageV2
      title={tool.name}
      mode="view"
      breadcrumbs={breadcrumbs}
      loading={false}
      backPath="/admin/tools"
    >
      <Tab
        title="Основное"
        layout="grid"
        id="overview"
      >
        <Block
          title="Deprecated"
          icon="alert-triangle"
          iconVariant="warn"
          width="full"
        >
          Этот экран относится к legacy tool-container/release модели и сохранен только для обратной совместимости.
        </Block>
        <Block
          title="Информация об инструменте"
          icon="tool"
          iconVariant="primary"
          width="2/3"
          fields={TOOL_INFO_FIELDS}
          data={toolData}
        />
        <Block
          title="Статистика"
          icon="bar-chart"
          iconVariant="info"
          width="1/3"
          fields={TOOL_STATS_FIELDS}
          data={statsData}
          editable={false}
        />
        <Block
          title="Основное"
          icon="info"
          iconVariant="primary"
          width="1/2"
          fields={TOOL_META_FIELDS}
          data={versionMetaData}
          editable={false}
        />
        {!!activeVersionData && (
          <Block
            title="Версия релиза"
            icon="history"
            iconVariant="info"
            width="1/2"
            fields={TOOL_META_FIELDS}
            data={versionMetaData}
            editable={false}
          />
        )}
        {!!tool.current_version?.backend_release && (
          <>
            <Block
              title="Backend release"
              icon="database"
              iconVariant="primary"
              width="1/2"
              fields={TOOL_BACKEND_RELEASE_INFO_FIELDS}
              data={buildToolBackendReleaseInfoData(tool.current_version.backend_release)}
              editable={false}
            />
            <Block
              title="Backend release meta"
              icon="clock"
              iconVariant="neutral"
              width="1/2"
              fields={TOOL_BACKEND_RELEASE_META_FIELDS}
              data={buildToolBackendReleaseMetaData(tool.current_version.backend_release)}
              editable={false}
            />
          </>
        )}
        {!hasRelease && (
          <Block
            title="Семантический релиз"
            icon="sparkles"
            iconVariant="warn"
            width="full"
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ color: 'var(--text-secondary)' }}>
                У этого backend-инструмента пока нет связанного релиза.
                Режим релизов для tool-container переведен в deprecated.
              </div>
            </div>
          </Block>
        )}
      </Tab>

      {!!activeVersionData && (
        <Tab title="Профайл" layout="grid" id="profile">
          <Block
            title="Профайл инструмента"
            icon="message-square"
            iconVariant="info"
            width="full"
            fields={TOOL_VERSION_PROFILE_FIELDS}
            data={activeVersionData}
            editable={false}
          />
        </Tab>
      )}

      {!!activeVersionData && (
        <Tab title="Policy Hints" layout="grid" id="policy-hints">
          <Block
            title="Правила использования"
            icon="shield"
            iconVariant="primary"
            width="full"
            fields={TOOL_VERSION_POLICY_FIELDS}
            data={activeVersionData}
            editable={false}
          />
        </Tab>
      )}

      {!!tool.backend_releases?.length && (
        <Tab title="Схемы" layout="full" id="backend" badge={tool.backend_releases.length}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {tool.backend_releases.map((release, index) => {
              const detail = backendReleaseDetails[index]?.data;
              return (
                <div key={release.id} style={{ display: 'grid', gap: 16 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
                    <Block
                      title="Input Schema"
                      icon="arrow-down"
                      iconVariant="info"
                      width="1/2"
                      fields={[buildJsonFieldConfig('input_schema', 'JSON')]}
                      data={{ input_schema: detail?.input_schema ?? {} }}
                      editable={false}
                    />
                    <Block
                      title="Output Schema"
                      icon="arrow-up"
                      iconVariant="success"
                      width="1/2"
                      fields={[buildJsonFieldConfig('output_schema', 'JSON')]}
                      data={{ output_schema: detail?.output_schema ?? {} }}
                      editable={false}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Tab>
      )}

      {!!id && (
        <Tab
          title="Версии релиза"
          layout="full"
          id="versions"
          badge={versionInfo.length}
        >
          <VersionsBlock
            entityType="tool"
            versions={versionInfo}
            recommendedVersionId={tool.current_version_id ?? undefined}
          />
        </Tab>
      )}
    </EntityPageV2>
  );
}

export default ToolPage;
