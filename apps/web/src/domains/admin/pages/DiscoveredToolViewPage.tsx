import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { discoveredToolsApi } from '@/shared/api/discoveredTools';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block } from '@/shared/ui/GridLayout';

const DESCRIPTION_FIELDS = [
  { key: 'slug', type: 'code' as const, label: 'Slug', editable: false },
  { key: 'name', type: 'text' as const, label: 'Имя', editable: false },
  { key: 'source', type: 'badge' as const, label: 'Источник', editable: false, badgeTone: 'info' as const },
  { key: 'connector', type: 'text' as const, label: 'Коннектор', editable: false },
  { key: 'domains', type: 'tags' as const, label: 'Домены', editable: false },
  { key: 'description', type: 'textarea' as const, label: 'Описание', editable: false },
];

const INPUT_SCHEMA_FIELDS = [
  { key: 'input_schema', type: 'json' as const, label: 'JSON Schema', editable: false },
];

const OUTPUT_SCHEMA_FIELDS = [
  { key: 'output_schema', type: 'json' as const, label: 'JSON Schema', editable: false },
];

export function DiscoveredToolViewPage() {
  const { id } = useParams<{ id: string }>();

  const { data: tool, isLoading } = useQuery({
    queryKey: qk.discoveredTools.detail(id || ''),
    queryFn: () => discoveredToolsApi.get(id || ''),
    enabled: Boolean(id),
    staleTime: 30_000,
  });

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: tool?.slug || id || '' },
  ];

  if (!tool) {
    return (
      <EntityPageV2
        title="Инструмент"
        mode="view"
        breadcrumbs={breadcrumbs}
        loading={isLoading}
        backPath="/admin/tools"
      >
        <></>
      </EntityPageV2>
    );
  }

  const connector = tool.connector_name
    ? `${tool.connector_slug || ''} (${tool.connector_name})`
    : (tool.connector_slug || '—');

  const descriptionData = {
    slug: tool.slug,
    name: tool.name,
    source: tool.source,
    connector,
    domains: tool.domains,
    description: tool.description || '—',
  };

  return (
    <EntityPageV2
      title={tool.name || tool.slug}
      mode="view"
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      backPath="/admin/tools"
    >
      <Tab title="Описание" layout="grid" id="description">
        <Block
          title="Описание"
          icon="info"
          iconVariant="primary"
          width="full"
          fields={DESCRIPTION_FIELDS}
          data={descriptionData}
          editable={false}
        />
      </Tab>

      <Tab title="Входная схема" layout="grid" id="input-schema">
        <Block
          title="Входная схема"
          icon="arrow-down"
          iconVariant="info"
          width="full"
          fields={INPUT_SCHEMA_FIELDS}
          data={{ input_schema: tool.input_schema || {} }}
          editable={false}
        />
      </Tab>

      <Tab title="Выходная схема" layout="grid" id="output-schema">
        <Block
          title="Выходная схема"
          icon="arrow-up"
          iconVariant="success"
          width="full"
          fields={OUTPUT_SCHEMA_FIELDS}
          data={{ output_schema: tool.output_schema || {} }}
          editable={false}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default DiscoveredToolViewPage;
