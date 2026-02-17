/**
 * AgentPage v2 - Container + Versions (like PolicyPage)
 *
 * Uses EntityTabsPage for unified layout.
 * Agent container: slug, name, description
 * Versions hold: prompt, policy_id, limit_id
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi, type AgentCreate, type AgentUpdate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui/EntityPage/EntityPageV2';
import { ConfirmDialog, ContentBlock, VersionsBlock, TagsInput, type FieldDefinition } from '@/shared/ui';
import { Button, Input } from '@/shared/ui';

export function AgentPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !slug || slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    tag: '',
    category: '',
    routing_example: '',
    is_routable: false,
  });

  const { data: agent, isLoading } = useQuery({
    queryKey: qk.agents.detail(slug!),
    queryFn: () => agentsApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  const activeVersion = agent?.versions?.find(v => v.status === 'active') || agent?.versions?.[0];

  useEffect(() => {
    if (agent) {
      setFormData({
        slug: agent.slug,
        name: agent.name,
        description: agent.description || '',
        tag: agent.tag || '',
        category: agent.category || '',
        routing_example: agent.routing_example || '',
        is_routable: agent.is_routable || false,
      });
    }
  }, [agent]);

  const createMutation = useMutation({
    mutationFn: (data: AgentCreate) => agentsApi.create(data),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент создан');
      navigate(`/admin/agents/${created.slug}`);
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: AgentUpdate) => agentsApi.update(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент обновлён');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка обновления'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => agentsApi.delete(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент удалён');
      navigate('/admin/agents');
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка удаления'),
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        if (!formData.slug.trim() || !formData.name.trim()) {
          showError('Заполните все обязательные поля');
          return;
        }
        await createMutation.mutateAsync(formData);
      } else {
        await updateMutation.mutateAsync({
          name: formData.name,
          description: formData.description,
          tag: formData.tag,
          category: formData.category,
          routing_example: formData.routing_example,
          is_routable: formData.is_routable,
        });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/agents');
    } else {
      if (agent) {
        setFormData({
          slug: agent.slug,
          name: agent.name,
          description: agent.description || '',
          tag: agent.tag || '',
          category: agent.category || '',
          routing_example: agent.routing_example || '',
          is_routable: agent.is_routable || false,
        });
      }
      setSearchParams({});
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
    await deleteMutation.mutateAsync();
  };

  const containerFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      required: true,
      disabled: !isNew,
      placeholder: 'network-assistant',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Network Engineer Helper',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание агента...',
      rows: 2,
    },
    {
      key: 'category',
      label: 'Категория',
      type: 'text',
      placeholder: 'support / analytics / devops',
    },
    {
      key: 'routing_example',
      label: 'Routing Example',
      type: 'textarea',
      placeholder: 'Пример запроса для роутера...',
      rows: 3,
    },
    {
      key: 'is_routable',
      label: 'Доступен для Agent Router',
      type: 'boolean',
      description: 'Если включено, роутер может выбрать этого агента автоматически',
    },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Агенты', href: '/admin/agents' },
    { label: agent?.name || 'Новый агент' },
  ];

  // Create mode — single tab
  if (isNew) {
    return (
      <EntityPageV2
        title="Новый агент"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/agents"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="single">
          <ContentBlock
            title="Основная информация"
            icon="info"
            fields={containerFields}
            data={formData}
            editable={true}
            onChange={handleFieldChange}
          />
          <ContentBlock title="Тег маршрутизации" icon="tag">
            <TagsInput
              value={formData.tag ? [formData.tag] : []}
              onChange={(tags) => handleFieldChange('tag', tags[0] || '')}
              maxTags={1}
              placeholder="Например: finance"
            />
          </ContentBlock>
        </Tab>
      </EntityPageV2>
    );
  }

  // View/Edit mode — two tabs
  return (
    <>
      <EntityPageV2
        title={agent?.name || 'Агент'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onSave={handleSave}
        onCancel={handleCancel}
        onDelete={handleDelete}
      >
        <Tab 
          title="Обзор" 
          layout="grid"
          actions={
            mode === 'view' ? [
              <Button key="edit" onClick={handleEdit}>
                Редактировать
              </Button>,
              <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
                Удалить
              </Button>,
            ] : mode === 'edit' ? [
              <Button key="save" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel}>
                Отмена
              </Button>,
            ] : []
          }
        >
          <ContentBlock
            title="Основная информация"
            icon="info"
            fields={containerFields}
            data={mode === 'edit' ? formData : {
              slug: agent?.slug || '',
              name: agent?.name || '',
              description: agent?.description || '',
              category: agent?.category || '',
              routing_example: agent?.routing_example || '',
              is_routable: agent?.is_routable || false,
            }}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />
          <ContentBlock title="Тег маршрутизации" icon="tag">
            {mode === 'edit' ? (
              <TagsInput
                value={formData.tag ? [formData.tag] : []}
                onChange={(tags) => handleFieldChange('tag', tags[0] || '')}
                maxTags={1}
                placeholder="Например: finance"
              />
            ) : (
              <Input value={agent?.tag || '—'} disabled />
            )}
          </ContentBlock>
          <ContentBlock
            title="Статистика"
            icon="bar-chart"
            fields={[
              { key: 'versions_count', label: 'Версий', type: 'text' },
              { key: 'active_version', label: 'Активная версия', type: 'text' },
            ]}
            data={{
              versions_count: agent?.versions?.length || 0,
              active_version: activeVersion?.version || '—',
            }}
          />
        </Tab>
        
        <Tab 
          title="Версии" 
          layout="full" 
          badge={agent?.versions?.length || 0}
          actions={[
            <Button key="create" onClick={() => navigate(`/admin/agents/${slug}/versions/new`)}>
              Создать версию
            </Button>,
          ]}
        >
          <VersionsBlock
            entityType="agent"
            versions={agent?.versions || []}
            selectedVersion={activeVersion}
            onSelectVersion={(version) => navigate(`/admin/agents/${slug}/versions/${version.version}`)}
          />
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить агента?"
        message={
          <div>
            <p>Вы уверены, что хотите удалить агента <strong>{agent?.name}</strong>?</p>
            <p>Это действие удалит все версии и привязки инструментов. Отменить его невозможно.</p>
          </div>
        }
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

export default AgentPage;
