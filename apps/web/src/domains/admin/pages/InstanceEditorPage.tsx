/**
 * InstanceEditorPage v2 - Create/Edit tool instance
 *
 * v2 fields: tool_group_id, name, url, description, config, is_active
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, toolGroupsApi, type ToolInstanceCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import styles from './InstanceEditorPage.module.css';

export function InstanceEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !id;
  const mode: EntityPageMode = isCreate ? 'create' : 'edit';
  const isEditable = true;

  const [formData, setFormData] = useState<ToolInstanceCreate & { is_active?: boolean }>({
    tool_group_id: '',
    name: '',
    url: '',
    description: '',
    config: {},
  });
  const [configText, setConfigText] = useState('{}');
  const [saving, setSaving] = useState(false);

  const { data: toolGroups } = useQuery({
    queryKey: qk.toolGroups.list(),
    queryFn: () => toolGroupsApi.listGroups(),
  });

  const { data: existingInstance, isLoading } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !isCreate && !!id,
  });

  useEffect(() => {
    if (existingInstance) {
      setFormData({
        tool_group_id: existingInstance.tool_group_id,
        name: existingInstance.name || '',
        url: existingInstance.url || '',
        description: existingInstance.description || '',
        config: existingInstance.config || {},
        is_active: existingInstance.is_active,
      });
      setConfigText(JSON.stringify(existingInstance.config || {}, null, 2));
    }
  }, [existingInstance]);

  const handleSave = async () => {
    setSaving(true);
    try {
      let config: Record<string, unknown> = {};
      if (configText.trim()) {
        config = JSON.parse(configText);
      }

      if (isCreate) {
        if (!formData.tool_group_id || formData.tool_group_id.trim() === '') {
          showError('Выберите группу инструментов');
          return;
        }
        if (!formData.name || formData.name.trim() === '') {
          showError('Введите название инстанса');
          return;
        }
        await toolInstancesApi.create({ ...formData, config });
        showSuccess('Инстанс создан');
        queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
        navigate('/admin/instances');
      } else {
        await toolInstancesApi.update(id!, {
          name: formData.name,
          url: formData.url,
          description: formData.description,
          config,
          is_active: formData.is_active,
        });
        showSuccess('Инстанс обновлён');
        queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
        queryClient.invalidateQueries({ queryKey: qk.toolInstances.detail(id!) });
        navigate(`/admin/instances/${id}`);
      }
    } catch (err) {
      if (err instanceof SyntaxError) {
        showError('Невалидный JSON в конфигурации');
      } else {
        showError(err instanceof Error ? err.message : 'Ошибка сохранения');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (isCreate) {
      navigate('/admin/instances');
    } else {
      navigate(`/admin/instances/${id}`);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Удалить этот инстанс?')) return;
    try {
      await toolInstancesApi.delete(id!);
      showSuccess('Инстанс удалён');
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      navigate('/admin/instances');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const basicFields: FieldDefinition[] = [
    {
      key: 'tool_group_id',
      label: 'Группа инструментов',
      type: 'select',
      required: true,
      disabled: !isCreate,
      options: toolGroups?.map((g: any) => ({
        value: g.id,
        label: `${g.name} (${g.slug})`,
      })) || [],
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Production NetBox',
    },
    {
      key: 'url',
      label: 'URL',
      type: 'text',
      placeholder: 'https://netbox.example.com/api',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание инстанса...',
      rows: 2,
    },
  ];

  const statusFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Активен',
      type: 'boolean',
      description: 'Неактивные инстансы не используются при выполнении запросов',
    },
  ];

  const breadcrumbs = [
    { label: 'Инстансы', href: '/admin/instances' },
    { label: existingInstance?.name || 'Новый инстанс' },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={existingInstance?.name || 'Новый инстанс'}
      entityTypeLabel="инстанса"
      backPath="/admin/instances"
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={!isCreate ? handleDelete : undefined}
      showDelete={!isCreate}
    >
      <ContentGrid>
        <ContentBlock
          width="2/3"
          title="Основные параметры"
          icon="server"
          editable={isEditable}
          fields={basicFields}
          data={formData}
          onChange={handleFieldChange}
        />

        <ContentBlock
          width="1/3"
          title="Статус"
          icon="toggle-left"
          editable={isEditable}
          fields={statusFields}
          data={formData}
          onChange={handleFieldChange}
        />

        <ContentBlock
          width="2/3"
          title="Конфигурация (JSON)"
          icon="settings"
        >
          {isEditable ? (
            <>
              <Textarea
                className={styles.codeEditor}
                value={configText}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setConfigText(e.target.value)}
                placeholder='{"timeout": 30, "headers": {}}'
                rows={10}
              />
              <span className={styles.formHint}>
                Дополнительные параметры подключения в формате JSON
              </span>
            </>
          ) : (
            <pre className={styles.codeView}>{configText}</pre>
          )}
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}

export default InstanceEditorPage;
