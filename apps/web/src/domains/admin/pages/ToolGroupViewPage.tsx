/**
 * ToolGroupViewPage - View/Edit tool group
 * 
 * Layout similar to PromptEditorPage:
 * - Left column (1/2): Group info (editable name, description)
 * - Right column (1/2): Tools table
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolGroupsApi, toolsApi, type ToolGroup, type Tool } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import Badge from '@/shared/ui/Badge';
import styles from './PromptEditorPage.module.css';

const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  function: 'Функция',
  database: 'База данных',
  builtin: 'Встроенный',
};

const TYPE_TONES: Record<string, 'warn' | 'success' | 'info' | 'neutral'> = {
  api: 'info',
  function: 'success',
  database: 'warn',
  builtin: 'neutral',
};

export function ToolGroupViewPage() {
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit';

  // Form state
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
  });
  const [saving, setSaving] = useState(false);

  // Load group
  const { data: group, isLoading: groupLoading } = useQuery({
    queryKey: qk.toolGroups.detail(groupId!),
    queryFn: () => toolGroupsApi.get(groupId!),
    enabled: !!groupId,
  });

  // Load tools in group
  const { data: tools, isLoading: toolsLoading } = useQuery({
    queryKey: ['tools', 'list', { tool_group_id: groupId }],
    queryFn: () => toolsApi.list({ tool_group_id: groupId }),
    enabled: !!groupId,
  });

  // Sync form data
  useEffect(() => {
    if (group) {
      setFormData({
        slug: group.slug,
        name: group.name,
        description: group.description || '',
      });
    }
  }, [group]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: () => toolGroupsApi.update(groupId!, {
      name: formData.name,
      description: formData.description,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.toolGroups.detail(groupId!) });
      queryClient.invalidateQueries({ queryKey: qk.toolGroups.list({}) });
      showSuccess('Группа обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка обновления'),
  });

  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMutation.mutateAsync();
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (group) {
      setFormData({
        slug: group.slug,
        name: group.name,
        description: group.description || '',
      });
    }
    setSearchParams({});
  };

  const handleFieldChange = (key: string, value: string) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleToolClick = (tool: Tool) => {
    navigate(`/admin/tools/groups/${groupId}/tools/${tool.slug}`);
  };

  // Field definitions
  const groupFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      disabled: true,
      description: 'Уникальный идентификатор (создаётся автоматически)',
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'RAG',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание группы инструментов...',
      rows: 2,
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={group?.name || 'Группа инструментов'}
      entityTypeLabel="группы"
      backPath="/admin/tools"
      loading={groupLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
    >
      <ContentGrid>
        {/* Group Info - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Информация о группе"
          icon="folder"
          editable={isEditable}
          fields={groupFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Tools Table - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Инструменты"
          icon="tool"
        >
          {toolsLoading ? (
            <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>Загрузка...</p>
          ) : tools && tools.length > 0 ? (
            <div className={styles.versionsTable}>
              <table>
                <thead>
                  <tr>
                    <th>Slug / Имя</th>
                    <th>Тип</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((tool: Tool) => (
                    <tr
                      key={tool.id}
                      onClick={() => handleToolClick(tool)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <strong>{tool.slug}</strong>
                        <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                          {tool.name}
                        </div>
                      </td>
                      <td>
                        <Badge tone={TYPE_TONES[tool.type] || 'neutral'} size="small">
                          {TYPE_LABELS[tool.type] || tool.type}
                        </Badge>
                      </td>
                      <td>
                        <Badge tone={tool.is_active ? 'success' : 'neutral'} size="small">
                          {tool.is_active ? 'Активен' : 'Неактивен'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>
              В этой группе пока нет инструментов.
            </p>
          )}
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}

export default ToolGroupViewPage;
