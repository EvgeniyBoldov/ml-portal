/**
 * AgentEditorPage v2 - Container + Versions (like PolicyEditorPage)
 *
 * Uses EntityTabsPage for unified layout.
 * Agent container: slug, name, description
 * Versions hold: prompt, policy_id, limit_id
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi, type AgentDetail, type AgentVersionInfo } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityTabsPage, PromptVersionCard, type FieldDefinition, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui';

export function AgentEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const [saving, setSaving] = useState(false);

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
  const { data: selectedVersion } = useQuery({
    queryKey: qk.agents.version(slug!, activeVersion?.version ?? 0),
    queryFn: () => agentsApi.getVersion(slug!, activeVersion!.version),
    enabled: !!slug && !!activeVersion,
  });

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
    mutationFn: (data: any) => agentsApi.create(data),
    onSuccess: (created: any) => {
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент создан');
      navigate(`/admin/agents/${created.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => agentsApi.update(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.agents.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.agents.list() });
      showSuccess('Агент обновлён');
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
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

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
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

  return (
    <EntityTabsPage
      entityType="policy"
      entityNameLabel="Агент"
      entityTypeLabel="агента"
      slug={slug!}
      basePath="/admin/agents"
      listPath="/admin/agents"
      container={agent || null}
      versions={agent?.versions || []}
      isLoading={isLoading}
      formData={formData}
      mode={mode}
      saving={saving}
      onFieldChange={handleFieldChange}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onCreateVersion={() => navigate(`/admin/agents/${slug}/versions/new`)}
      onSelectVersion={(v: AgentVersionInfo) => navigate(`/admin/agents/${slug}/versions/${v.version}`)}
      containerFields={containerFields}
      breadcrumbs={breadcrumbs}
      renderVersionContent={() => (
        <PromptVersionCard
          version={selectedVersion ? { ...selectedVersion, template: selectedVersion.prompt } : null}
          onCreateVersion={() => navigate(`/admin/agents/${slug}/versions/new`)}
        />
      )}
    />
  );
}

export default AgentEditorPage;
