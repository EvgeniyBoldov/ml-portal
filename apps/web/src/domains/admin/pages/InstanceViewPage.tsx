/**
 * InstanceViewPage - View tool instance details
 * 
 * Uses EntityPage + ContentBlock from shared/ui
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolInstancesApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { EntityPage, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { ContentBlock, type FieldDefinition } from '@/shared/ui/ContentBlock';
import { Badge } from '@/shared/ui';

export function InstanceViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: instance, isLoading } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !!id,
  });

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Инстансы', href: '/admin/instances' },
    { label: instance?.name || instance?.tool?.name || 'Инстанс' },
  ];

  const infoFields: FieldDefinition[] = [
    {
      key: 'tool_name',
      label: 'Инструмент',
      type: 'text',
      disabled: true,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      disabled: true,
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      disabled: true,
      rows: 2,
    },
  ];

  const formData = {
    tool_name: instance?.tool?.name || instance?.tool_id || '',
    name: instance?.name || '',
    description: instance?.tool?.description || '',
  };

  return (
    <EntityPage
      mode="view"
      entityName={instance?.name || instance?.tool?.name || 'Инстанс'}
      entityTypeLabel="инстанса"
      backPath="/admin/instances"
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      showDelete={false}
      onEdit={() => navigate(`/admin/instances/${id}/edit`)}
    >
      <ContentBlock
        title="Основные параметры"
        icon="server"
        fields={infoFields}
        data={formData}
        headerActions={
          <Badge tone={instance?.is_active ? 'success' : 'neutral'} size="small">
            {instance?.is_active ? 'Активен' : 'Неактивен'}
          </Badge>
        }
      />

      <ContentBlock
        title="Конфигурация"
        icon="settings"
      >
          <pre style={{
            background: 'var(--bg-secondary)',
            padding: '1rem',
            borderRadius: '8px',
            overflow: 'auto',
            fontSize: '0.875rem',
            margin: 0,
          }}>
            {JSON.stringify(instance?.config || {}, null, 2)}
          </pre>
      </ContentBlock>

      {instance?.health_status && (
          <ContentBlock
            title="Health Check"
            icon="activity"
            fields={[
              {
                key: 'health_status',
                label: 'Статус',
                type: 'badge' as any,
                badgeTone: instance.health_status === 'healthy' ? 'success' : 'danger',
                disabled: true,
              },
              ...(instance.last_health_check ? [{
                key: 'last_health_check',
                label: 'Последняя проверка',
                type: 'text' as any,
                disabled: true,
              }] : []),
            ]}
            data={{
              health_status: instance.health_status,
              last_health_check: instance.last_health_check
                ? new Date(instance.last_health_check).toLocaleString('ru')
                : '',
            }}
          />
      )}
    </EntityPage>
  );
}

export default InstanceViewPage;
