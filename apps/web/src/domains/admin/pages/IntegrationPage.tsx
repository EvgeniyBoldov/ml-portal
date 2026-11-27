import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  assignmentIntegrationsApi,
  type AssignmentIntegration,
  type IntegrationCreate,
  type IntegrationSettings,
} from '@/shared/api/assignmentIntegrations';
import { qk } from '@/shared/api/keys';
import { toolInstancesApi } from '@/shared/api/toolInstances';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { Button, EntityPageV2, Tab } from '@/shared/ui';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { IntegrationTokensPanel } from './IntegrationTokensPanel';

const connectorFilter = { connector_type: 'integration', placement: 'remote' };
const backPath = '/admin/platform?tab=integrations';
const sourcePattern = /^[a-z0-9][a-z0-9_-]{0,47}:[a-z0-9][a-z0-9_-]{0,47}$/;

export function useIntegrationConnectors() {
  return useQuery({
    queryKey: qk.toolInstances.list(connectorFilter),
    queryFn: () => toolInstancesApi.list(connectorFilter),
  });
}

function validateSettings(data: IntegrationSettings) {
  if (!data.name.trim()) return 'Введите название';
  if (!data.connector_id) return 'Выберите коннектор для ответа';
  return null;
}

export default function IntegrationPage() {
  const [issuing, setIssuing] = useState(false);
  const editor = useEntityEditor<AssignmentIntegration, IntegrationCreate, IntegrationSettings>({
    entityType: 'integration',
    entityTypeLabel: 'интеграцию',
    entityNameLabel: 'Интеграции',
    basePath: '/admin/integrations',
    listPath: backPath,
    api: assignmentIntegrationsApi,
    queryKeys: qk.assignmentIntegrations,
    getInitialFormData: (value) => ({
      name: value?.name ?? '',
      source: value?.source ?? '',
      connector_id: value?.connector_id ?? '',
      is_active: value?.is_active ?? true,
    }),
    validateCreate: (data) =>
      validateSettings(data) || (sourcePattern.test(data.source.trim()) ? null : 'Укажите идентификатор в формате тип:id'),
    validateUpdate: validateSettings,
    transformCreate: (data) => ({ ...data, source: data.source.trim() }),
    transformUpdate: ({ name, connector_id, is_active }) => ({ name, connector_id, is_active }),
    messages: { create: 'Интеграция создана', update: 'Интеграция обновлена' },
  });
  const { data: connectors = [], isError } = useIntegrationConnectors();
  const fields: FieldConfig[] = [
    { key: 'name', type: 'text', label: 'Название', required: true },
    {
      key: 'source', type: 'text', label: 'Идентификатор источника', required: true,
      placeholder: 'clouds:express', editable: editor.isNew,
      description: 'Значение заголовка X-Assignment-Connector во входящих запросах.',
    },
    {
      key: 'connector_id', type: 'select', label: 'Коннектор для ответа', required: true,
      description: 'URL и авторизация исходящих запросов берутся из настроек коннектора.',
      options: connectors.map((connector) => ({ value: connector.id, label: connector.name })),
    },
    { key: 'is_active', type: 'boolean', label: 'Активна', description: 'Разрешает запросы с токенами этой интеграции.' },
  ];

  return (
    <EntityPageV2
      title={editor.isNew ? 'Новая интеграция' : (editor.entity?.name ?? 'Интеграция')}
      mode={editor.mode}
      breadcrumbs={editor.breadcrumbs}
      backPath={backPath}
      loading={editor.isLoading}
      saving={editor.saving}
      onSave={editor.handleSave}
      onCancel={editor.handleCancel}
    >
      <Tab
        id="settings"
        title="Настройки"
        layout="grid"
        actions={editor.isNew ? undefined : buildEntityCrudActions({
          mode: editor.mode,
          saving: editor.saving,
          onEdit: editor.handleEdit,
          onSave: editor.handleSave,
          onCancel: editor.handleCancel,
        })}
      >
        {isError && <p role="alert">Не удалось загрузить коннекторы.</p>}
        {!editor.isNew && !editor.isLoading && !editor.entity && <p role="alert">Не удалось загрузить интеграцию.</p>}
        {(editor.isNew || editor.entity) && (
          <Block
            title="Основные настройки"
            width="full"
            fields={fields}
            data={editor.isEditable ? editor.formData : editor.entity}
            editable={editor.isEditable}
            onChange={editor.handleFieldChange}
          />
        )}
      </Tab>
      {editor.entity && (
        <Tab
          id="tokens"
          title="Токены авторизации"
          layout="full"
          actions={[<Button key="issue" onClick={() => setIssuing(true)}>Выпустить токен</Button>]}
        >
          <IntegrationTokensPanel
            key={editor.entity.id}
            integrationId={editor.entity.id}
            issuing={issuing}
            onClose={() => setIssuing(false)}
          />
        </Tab>
      )}
    </EntityPageV2>
  );
}
