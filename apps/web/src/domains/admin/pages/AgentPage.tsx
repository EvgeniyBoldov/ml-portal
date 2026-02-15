/**
 * AgentPage - View/Edit/Create agent with EntityPageV2
 * 
 * Unified page for all agent operations:
 * - View: /admin/agents/:slug (readonly)
 * - Edit: /admin/agents/:slug?mode=edit
 * - Create: /admin/agents/new
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi, type AgentCreate, type AgentUpdate, type Agent } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui/EntityPage/EntityPageV2';
import { PromptVersionCard, ConfirmDialog, ContentBlock, VersionsBlock, type FieldDefinition } from '@/shared/ui';
import { Button } from '@/shared/ui';

type ApiErrorShape = {
  message?: string;
};

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
      });
    }
  }, [agent]);

  const createMutation = useMutation({
    mutationFn: (data: AgentCreate) => agentsApi.create(data),
    onSuccess: (created: Agent) => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент создан');
      navigate(`/admin/agents/${created.slug}`);
    },
    onError: (err: unknown) => showError((err as ApiErrorShape)?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: AgentUpdate) => agentsApi.update(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент обновлён');
      setSearchParams({});
    },
    onError: (err: unknown) => showError((err as ApiErrorShape)?.message || 'Ошибка обновления'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => agentsApi.delete(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент удалён');
      navigate('/admin/agents');
    },
    onError: (err: unknown) => showError((err as ApiErrorShape)?.message || 'Ошибка удаления'),
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
        });
      }
      setSearchParams({});
    }
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
      >
        <Tab title="Создание" layout="single">
          <PromptVersionCard
            version={null}
            onCreateVersion={() => navigate(`/admin/agents/${slug}/versions/new`)}
          />
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
            fields={[
              { key: 'slug', label: 'Slug', type: 'text' },
              { key: 'name', label: 'Название', type: 'text' },
              { key: 'description', label: 'Описание', type: 'textarea' },
            ]}
            data={{
              slug: agent?.slug || '',
              name: agent?.name || '',
              description: agent?.description || '',
            }}
          />
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
          {(() => {
            const normalizedVersions = (agent?.versions || []).map(version => ({
              ...version,
              notes: version.notes ?? undefined,
            }));
            const normalizedSelectedVersion = activeVersion
              ? { ...activeVersion, notes: activeVersion.notes ?? undefined }
              : undefined;

            return (
          <VersionsBlock
            entityType="agent"
            versions={normalizedVersions}
            selectedVersion={normalizedSelectedVersion}
            onSelectVersion={(version) => navigate(`/admin/agents/${slug}/versions/${version.version}`)}
          />
            );
          })()}
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
