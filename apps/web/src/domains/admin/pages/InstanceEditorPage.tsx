/**
 * InstanceEditorPage - View/Edit/Create tool instance with EntityPage
 * 
 * Unified page for all instance operations:
 * - View: /admin/instances/:id (readonly)
 * - Edit: /admin/instances/:id?mode=edit
 * - Create: /admin/instances/new
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, toolsApi, type ToolInstanceCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import styles from './InstanceEditorPage.module.css';

export function InstanceEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // Determine mode
  const isCreate = !id;
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<ToolInstanceCreate & { name?: string; description?: string }>({
    tool_id: '',
    name: '',
    description: '',
    scope: 'default',
    is_active: true,
    config: {},
  });
  const [configText, setConfigText] = useState('{}');
  const [saving, setSaving] = useState(false);

  // Load tools for dropdown
  const { data: tools } = useQuery({
    queryKey: qk.tools.list(),
    queryFn: () => toolsApi.list(),
  });

  // Load existing instance
  const { data: existingInstance, isLoading, refetch } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !isCreate,
  });

  useEffect(() => {
    if (existingInstance) {
      setFormData({
        tool_id: existingInstance.tool_id,
        name: (existingInstance as any).name || '',
        description: (existingInstance as any).description || '',
        scope: existingInstance.scope,
        is_active: existingInstance.is_active,
        config: existingInstance.config || {},
      });
      setConfigText(JSON.stringify(existingInstance.config || {}, null, 2));
    }
  }, [existingInstance]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const config = JSON.parse(configText);
      const data = { ...formData, config };
      
      if (mode === 'create') {
        await toolInstancesApi.create(data);
        showSuccess('Инстанс создан');
        queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
        navigate('/admin/instances');
      } else {
        await toolInstancesApi.update(id!, data);
        showSuccess('Инстанс обновлён');
        queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
        setSearchParams({});
        refetch();
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

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (mode === 'edit' && existingInstance) {
      setFormData({
        tool_id: existingInstance.tool_id,
        scope: existingInstance.scope,
        is_active: existingInstance.is_active,
        config: existingInstance.config || {},
      });
      setConfigText(JSON.stringify(existingInstance.config || {}, null, 2));
      setSearchParams({});
    } else if (mode === 'create') {
      navigate('/admin/instances');
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

  const getToolName = (toolId: string) => {
    const tool = tools?.find((t: { id: string; name: string }) => t.id === toolId);
    return tool?.name || toolId;
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: ToolInstanceCreate) => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const basicFields: FieldDefinition[] = [
    {
      key: 'tool_id',
      label: 'Инструмент',
      type: 'select',
      required: true,
      disabled: mode !== 'create',
      options: [
        { value: '', label: 'Выберите инструмент' },
        ...(tools?.map((t: { id: string; name: string; slug: string }) => ({
          value: t.id,
          label: `${t.name} (${t.slug})`,
        })) || []),
      ],
      description: mode === 'create' ? 'Инструмент, для которого создаётся инстанс' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      placeholder: 'Название инстанса',
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

  return (
    <EntityPage
      mode={mode}
      entityName={existingInstance ? getToolName(existingInstance.tool_id) : 'Новый инстанс'}
      entityTypeLabel="инстанса"
      backPath="/admin/instances"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id}
    >
      <ContentGrid>
        {/* Basic Info - 2/3 */}
        <ContentBlock
          width="2/3"
          title="Основные параметры"
          icon="tool"
          editable={isEditable}
          fields={basicFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Status - 1/3 */}
        <ContentBlock
          width="1/3"
          title="Статус"
          icon="toggle-left"
          editable={isEditable}
          fields={statusFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Config - 2/3 (JSON редактор) */}
        <ContentBlock
          width="2/3"
          title="Конфигурация"
          icon="settings"
        >
          {isEditable ? (
            <>
              <Textarea
                className={styles.codeEditor}
                value={configText}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setConfigText(e.target.value)}
                placeholder='{"endpoint": "https://...", "timeout": 30}'
                rows={12}
              />
              <span className={styles.formHint}>
                Параметры подключения: endpoint, timeout, max_retries, headers и т.д.
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
