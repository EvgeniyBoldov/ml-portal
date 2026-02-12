/**
 * ViewBackendReleasePage - View backend release details
 * 
 * Shows meta info + input/output schemas
 * Route: /admin/tools/:toolSlug/backend/:version
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { 
  toolReleasesApi, 
  toolReleasesKeys,
} from '@/shared/api/toolReleases';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui/EntityPage/EntityPageV2';
import { ContentBlock, Badge, JSONDisplay, type FieldDefinition } from '@/shared/ui';

export function ViewBackendReleasePage() {
  const { toolSlug, version } = useParams<{ toolSlug: string; version: string }>();
  const navigate = useNavigate();

  const { data: tool } = useQuery({
    queryKey: toolReleasesKeys.toolDetail(toolSlug!),
    queryFn: () => toolReleasesApi.getTool(toolSlug!),
    enabled: !!toolSlug,
  });

  const { data: release, isLoading } = useQuery({
    queryKey: toolReleasesKeys.backendReleaseDetail(toolSlug!, version!),
    queryFn: () => toolReleasesApi.getBackendRelease(toolSlug!, version!),
    enabled: !!toolSlug && !!version,
  });

  const breadcrumbs = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: tool?.name || toolSlug || '', href: `/admin/tools/${toolSlug}` },
    { label: `Бэкенд ${version}` },
  ];

  const metaFields: FieldDefinition[] = [
    { key: 'version', label: 'Версия', type: 'text' },
    { key: 'method_name', label: 'Метод', type: 'text' },
    { key: 'schema_hash', label: 'Хеш схемы', type: 'text' },
    { key: 'worker_build_id', label: 'Worker Build ID', type: 'text' },
    { key: 'description', label: 'Описание', type: 'text' },
    { key: 'synced_at', label: 'Синхронизировано', type: 'text' },
  ];

  const metaData = release ? {
    version: release.version,
    method_name: release.method_name,
    schema_hash: release.schema_hash || '—',
    worker_build_id: release.worker_build_id || '—',
    description: release.description || '—',
    synced_at: new Date(release.synced_at).toLocaleString('ru-RU'),
  } : {};

  const methodSchema = release ? JSON.stringify({
    method_name: release.method_name,
    schema_hash: release.schema_hash,
    worker_build_id: release.worker_build_id,
  }, null, 2) : '';

  const inputFields: FieldDefinition[] = [];
  const inputSchema = release ? JSON.stringify(release.input_schema, null, 2) : '';

  const outputFields: FieldDefinition[] = [];
  const outputSchema = release ? JSON.stringify(release.output_schema, null, 2) : '';

  return (
    <EntityPageV2
      title={`Бэкенд-релиз ${version}`}
      mode="view"
      loading={isLoading}
      breadcrumbs={breadcrumbs}
      backPath={`/admin/tools/${toolSlug}`}
    >
      <Tab title="Мета-информация" layout="full">
        <ContentBlock
          width="full"
          title="Мета-информация"
          icon="info"
          fields={metaFields}
          data={metaData}
          headerActions={
            release ? (
              <Badge tone={release.deprecated ? 'warn' : 'success'} size="small">
                {release.deprecated ? 'Устарела' : 'Актуальна'}
              </Badge>
            ) : undefined
          }
        />
      </Tab>
      
      <Tab title="Входная схема" layout="full">
        <ContentBlock
          width="full"
          title="Входная схема"
          icon="arrow-down"
        >
          <JSONDisplay value={inputSchema} />
        </ContentBlock>
      </Tab>
      
      <Tab title="Выходная схема" layout="full">
        <ContentBlock
          width="full"
          title="Выходная схема"
          icon="arrow-up"
        >
          <JSONDisplay value={outputSchema} />
        </ContentBlock>
      </Tab>
      
      <Tab title="Метод и хеш" layout="full">
        <ContentBlock
          width="full"
          title="Метаданные метода"
          icon="settings"
        >
          <JSONDisplay value={methodSchema} />
        </ContentBlock>
      </Tab>
    </EntityPageV2>
  );
}

export default ViewBackendReleasePage;
