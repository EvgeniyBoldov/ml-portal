/**
 * ToolEditorPage - View/Edit tool with EntityPage
 * 
 * Инструменты подтягиваются с бэкенда, создание не поддерживается.
 * Редактируемые поля: name, description, is_active
 * Read-only: slug, type, input_schema, output_schema
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toolsApi, type Tool, type ToolUpdate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import Badge from '@/shared/ui/Badge';
import styles from './ToolEditorPage.module.css';

const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  function: 'Функция',
  database: 'База данных',
  builtin: 'Встроенный',
};

export function ToolEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // No create mode - tools come from backend
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit';

  const [formData, setFormData] = useState<ToolUpdate>({
    name: '',
    description: '',
    is_active: true,
  });
  const [saving, setSaving] = useState(false);

  // Load tool
  const { data: tool, isLoading, refetch } = useQuery({
    queryKey: qk.tools.detail(slug!),
    queryFn: () => toolsApi.get(slug!),
    enabled: !!slug,
  });

  useEffect(() => {
    if (tool) {
      setFormData({
        name: tool.name,
        description: tool.description || '',
        is_active: tool.is_active,
      });
    }
  }, [tool]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await toolsApi.update(slug!, formData);
      showSuccess('Инструмент обновлён');
      queryClient.invalidateQueries({ queryKey: qk.tools.all() });
      setSearchParams({});
      refetch();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (tool) {
      setFormData({
        name: tool.name,
        description: tool.description || '',
        is_active: tool.is_active,
      });
    }
    setSearchParams({});
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: ToolUpdate) => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const basicInfoFields: FieldDefinition[] = [
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Название инструмента',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание инструмента...',
      rows: 2,
    },
  ];

  const statusFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Активен',
      type: 'boolean',
      description: 'Инструмент доступен для использования агентами',
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={tool?.name || 'Инструмент'}
      entityTypeLabel="инструмента"
      backPath="/admin/tools"
      loading={isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
    >
      <ContentGrid>
        {/* Basic Info - 2/3 (редактируемые поля + метаданные) */}
        <ContentBlock
          width="2/3"
          title="Основная информация"
          icon="info"
          editable={isEditable}
          fields={basicInfoFields}
          data={formData}
          onChange={handleFieldChange}
        >
          <div className={styles.metaGrid}>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Slug</span>
              <code className={styles.metaValue}>{tool?.slug}</code>
            </div>
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Тип</span>
              <Badge tone="info">{TYPE_LABELS[tool?.type || ''] || tool?.type}</Badge>
            </div>
          </div>
        </ContentBlock>

        {/* Status - 1/3 (переключатель) */}
        <ContentBlock
          width="1/3"
          title="Статус"
          icon="toggle-left"
          editable={isEditable}
          fields={statusFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Input Schema - 1/2 (read-only) */}
        <ContentBlock
          width="1/2"
          title="Входная схема"
          icon="log-in"
        >
          <pre className={styles.schemaBlock}>
            {JSON.stringify(tool?.input_schema, null, 2)}
          </pre>
        </ContentBlock>

        {/* Output Schema - 1/2 (read-only) */}
        <ContentBlock
          width="1/2"
          title="Выходная схема"
          icon="log-out"
        >
          <pre className={styles.schemaBlock}>
            {tool?.output_schema 
              ? JSON.stringify(tool.output_schema, null, 2)
              : 'Не определена'
            }
          </pre>
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}

export default ToolEditorPage;
