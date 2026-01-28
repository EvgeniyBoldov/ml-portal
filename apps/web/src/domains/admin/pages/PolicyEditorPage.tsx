/**
 * PolicyEditorPage - View/Edit/Create permission policy with EntityPage
 * 
 * Unified page for all policy operations:
 * - View: /admin/policies/:id (readonly)
 * - Edit: /admin/policies/:id?mode=edit
 * - Create: /admin/policies/new
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { permissionsApi, toolsApi, type PermissionSetCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import styles from './PolicyEditorPage.module.css';

export function PolicyEditorPage() {
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

  const [formData, setFormData] = useState<PermissionSetCreate>({
    scope: 'default',
    tenant_id: undefined,
    user_id: undefined,
    allowed_tools: [],
    denied_tools: [],
    allowed_collections: [],
    denied_collections: [],
    is_active: true,
  });
  const [saving, setSaving] = useState(false);

  // Load tools for selection
  const { data: tools } = useQuery({
    queryKey: qk.tools.list(),
    queryFn: () => toolsApi.list(),
  });

  // Load existing policy
  const { data: existingPolicy, isLoading, refetch } = useQuery({
    queryKey: qk.permissions.detail(id!),
    queryFn: () => permissionsApi.get(id!),
    enabled: !isCreate,
  });

  useEffect(() => {
    if (existingPolicy) {
      setFormData({
        scope: existingPolicy.scope,
        tenant_id: existingPolicy.tenant_id,
        user_id: existingPolicy.user_id,
        allowed_tools: existingPolicy.allowed_tools || [],
        denied_tools: existingPolicy.denied_tools || [],
        allowed_collections: existingPolicy.allowed_collections || [],
        denied_collections: existingPolicy.denied_collections || [],
        is_active: existingPolicy.is_active,
      });
    }
  }, [existingPolicy]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const data = {
        ...formData,
        tenant_id: formData.scope === 'tenant' || formData.scope === 'user' ? formData.tenant_id : undefined,
        user_id: formData.scope === 'user' ? formData.user_id : undefined,
      };
      
      if (mode === 'create') {
        await permissionsApi.create(data);
        showSuccess('Политика создана');
        queryClient.invalidateQueries({ queryKey: qk.permissions.all() });
        navigate('/admin/policies');
      } else {
        await permissionsApi.update(id!, data);
        showSuccess('Политика обновлена');
        queryClient.invalidateQueries({ queryKey: qk.permissions.all() });
        setSearchParams({});
        refetch();
      }
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
    if (mode === 'edit' && existingPolicy) {
      setFormData({
        scope: existingPolicy.scope,
        tenant_id: existingPolicy.tenant_id,
        user_id: existingPolicy.user_id,
        allowed_tools: existingPolicy.allowed_tools || [],
        denied_tools: existingPolicy.denied_tools || [],
        allowed_collections: existingPolicy.allowed_collections || [],
        denied_collections: existingPolicy.denied_collections || [],
        is_active: existingPolicy.is_active,
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate('/admin/policies');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Удалить эту политику?')) return;
    try {
      await permissionsApi.delete(id!);
      showSuccess('Политика удалена');
      queryClient.invalidateQueries({ queryKey: qk.permissions.all() });
      navigate('/admin/policies');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  const toggleTool = (slug: string, list: 'allowed' | 'denied') => {
    if (!isEditable) return;
    const key = list === 'allowed' ? 'allowed_tools' : 'denied_tools';
    const otherKey = list === 'allowed' ? 'denied_tools' : 'allowed_tools';
    const current = formData[key] || [];
    const other = formData[otherKey] || [];

    if (current.includes(slug)) {
      setFormData({ ...formData, [key]: current.filter((t: string) => t !== slug) });
    } else {
      setFormData({
        ...formData,
        [key]: [...current, slug],
        [otherKey]: other.filter((t: string) => t !== slug),
      });
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: PermissionSetCreate) => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const scopeFields: FieldDefinition[] = [
    {
      key: 'scope',
      label: 'Уровень',
      type: 'select',
      required: true,
      disabled: mode !== 'create',
      options: [
        { value: 'default', label: 'По умолчанию (для всех)' },
        { value: 'tenant', label: 'Тенант' },
        { value: 'user', label: 'Пользователь' },
      ],
    },
    ...(formData.scope === 'tenant' || formData.scope === 'user' ? [{
      key: 'tenant_id',
      label: 'Tenant ID',
      type: 'text' as const,
      required: true,
      placeholder: 'UUID тенанта',
    }] : []),
    ...(formData.scope === 'user' ? [{
      key: 'user_id',
      label: 'User ID',
      type: 'text' as const,
      required: true,
      placeholder: 'UUID пользователя',
    }] : []),
    {
      key: 'is_active',
      label: 'Активна',
      type: 'boolean',
      description: 'Политика применяется к пользователям',
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={existingPolicy ? `Политика ${existingPolicy.scope}` : 'Новая политика'}
      entityTypeLabel="политики"
      backPath="/admin/policies"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id && existingPolicy?.scope !== 'default'}
    >
      <ContentGrid>
        {/* Scope - 1/3 (только выпадашки и переключатели) */}
        <ContentBlock
          width="1/3"
          title="Область применения"
          icon="shield"
          editable={isEditable}
          fields={scopeFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Tools - 2/3 (кастомный контент) */}
        <ContentBlock
          width="2/3"
          title="Инструменты"
          icon="tool"
        >
          {tools?.length ? (
            <div className={styles.toolsList}>
              {tools.map((tool: { slug: string; name: string }) => {
                const isAllowed = formData.allowed_tools?.includes(tool.slug);
                const isDenied = formData.denied_tools?.includes(tool.slug);
                return (
                  <div key={tool.slug} className={styles.toolItem}>
                    <div className={styles.toolInfo}>
                      <span className={styles.toolName}>{tool.name}</span>
                      <code className={styles.toolSlug}>{tool.slug}</code>
                    </div>
                    {isEditable ? (
                      <div className={styles.toolActions}>
                        <Button
                          type="button"
                          variant={isAllowed ? 'primary' : 'outline'}
                          size="sm"
                          onClick={() => toggleTool(tool.slug, 'allowed')}
                        >
                          ✓ Разрешить
                        </Button>
                        <Button
                          type="button"
                          variant={isDenied ? 'danger' : 'outline'}
                          size="sm"
                          onClick={() => toggleTool(tool.slug, 'denied')}
                        >
                          ✗ Запретить
                        </Button>
                      </div>
                    ) : (
                      <div>
                        {isAllowed && <Badge tone="success" size="small">Разрешён</Badge>}
                        {isDenied && <Badge tone="danger" size="small">Запрещён</Badge>}
                        {!isAllowed && !isDenied && <Badge tone="neutral" size="small">Не задано</Badge>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className={styles.emptyState}>
              Нет доступных инструментов
            </div>
          )}
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}

export default PolicyEditorPage;
