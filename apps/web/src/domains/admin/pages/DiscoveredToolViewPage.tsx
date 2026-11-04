import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { qk } from '@/shared/api/keys';
import { discoveredToolsApi } from '@/shared/api/discoveredTools';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block } from '@/shared/ui/GridLayout';
import { Badge, Button, Select } from '@/shared/ui';

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
  { key: 'output_schema', type: 'json' as const, label: 'Схема, объявленная провайдером', editable: false },
];

const OBSERVED_DATA_SCHEMA_FIELDS = [
  { key: 'observed_data_schema', type: 'json' as const, label: 'JSON Schema', editable: false },
];

export function DiscoveredToolViewPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [riskLevel, setRiskLevel] = useState('');
  const [resultDelivery, setResultDelivery] = useState<'direct' | 'store'>('direct');

  const { data: tool, isLoading, isError, refetch } = useQuery({
    queryKey: qk.discoveredTools.detail(id || ''),
    queryFn: () => discoveredToolsApi.get(id || ''),
    enabled: Boolean(id),
    staleTime: 30_000,
  });

  const updateMutation = useMutation({
    mutationFn: () => discoveredToolsApi.update(id || '', {
      risk_level: riskLevel,
      result_delivery: resultDelivery,
    }),
    onSuccess: (updated) => {
      queryClient.setQueryData(qk.discoveredTools.detail(id || ''), updated);
      queryClient.invalidateQueries({ queryKey: qk.discoveredTools.all() });
      setRiskLevel(updated.risk_level || '');
      setResultDelivery(updated.result_delivery);
      setEditing(false);
    },
  });

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инструменты', href: '/admin/tools' },
    { label: tool?.name || tool?.slug || id || '' },
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
        {isError && (
          <Tab title="Ошибка загрузки" layout="full">
            <p role="alert">
              Не удалось загрузить инструмент. <Button variant="outline" onClick={() => void refetch()}>Повторить</Button>
            </p>
          </Tab>
        )}
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
      mode={editing ? 'edit' : 'view'}
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      saving={updateMutation.isPending}
      backPath="/admin/tools"
      onEdit={() => {
        setRiskLevel(tool.risk_level || '');
        setResultDelivery(tool.result_delivery);
        setEditing(true);
      }}
      onCancel={() => setEditing(false)}
      onSave={() => updateMutation.mutate()}
    >
      {updateMutation.isError && (
        <p role="alert">Не удалось сохранить настройки инструмента. Проверьте значения и попробуйте снова.</p>
      )}
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
        <Block
          title="Уровень риска"
          icon="shield"
          iconVariant="warning"
          width="full"
          fields={[{
            key: 'risk_level',
            type: 'custom',
          label: 'Классификация риска операции',
            render: (value, editable) => editable
              ? <Select
                  value={riskLevel}
                  onChange={setRiskLevel}
                  placeholder="Не классифицировано"
                  options={[
                    { value: '', label: 'Не классифицировано' },
                    { value: 'safe', label: 'Безопасная' },
                    { value: 'risky', label: 'Рискованная' },
                  ]}
                />
              : <span>{value === 'safe' ? 'Безопасная' : value === 'risky' ? 'Рискованная' : 'Не классифицировано'}</span>,
          }]}
          data={{ risk_level: tool.risk_level || '' }}
          editable={editing}
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

      <Tab title="Схема провайдера" layout="grid" id="output-schema">
        <Block
          title="Объявленная схема ответа провайдера"
          icon="arrow-up"
          iconVariant="success"
          width="full"
          fields={OUTPUT_SCHEMA_FIELDS}
          data={{ output_schema: tool.output_schema || {} }}
          editable={false}
        />
      </Tab>

      <Tab title="Схема данных" layout="grid" id="observed-data-schema">
        <Block
          title="Наблюдаемая схема данных"
          icon="arrow-up"
          iconVariant="success"
          width="full"
          fields={tool.has_observed_data_schema ? OBSERVED_DATA_SCHEMA_FIELDS : undefined}
          data={{ observed_data_schema: tool.observed_data_schema || {} }}
          editable={false}
          headerLabels={(
            <Badge tone={tool.has_observed_data_schema ? 'success' : 'neutral'}>
              {tool.has_observed_data_schema ? 'Получена из ответа' : 'Пока нет'}
            </Badge>
          )}
        >
          {!tool.has_observed_data_schema && (
            <p>Схема появится после успешного вызова инструмента.</p>
          )}
        </Block>
        <Block
          title="Режим результата"
          icon="database"
          iconVariant="primary"
          width="full"
          fields={[{
            key: 'result_delivery',
            type: 'custom',
            label: 'Доставка результата',
            render: (value, isEditable) => isEditable
              ? <Select
                  value={resultDelivery}
                  onChange={(nextValue) => setResultDelivery(nextValue === 'store' ? 'store' : 'direct')}
                  options={[
                    { value: 'direct', label: 'Direct — передавать ответ напрямую' },
                    { value: 'store', label: 'Store — сохранять как набор данных' },
                  ]}
                />
              : <span>{value === 'store' ? 'Store — набор данных' : 'Direct — прямой ответ'}</span>,
          }]}
          data={{ result_delivery: tool.result_delivery }}
          editable={editing}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default DiscoveredToolViewPage;
