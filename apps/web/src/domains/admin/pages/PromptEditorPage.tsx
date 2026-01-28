/**
 * PromptEditorPage - View/Edit prompt container with versions
 * 
 * Layout:
 * - Left column (1/2): Container info + Versions table
 * - Right column (1/2): Selected version template + status
 * 
 * Features:
 * - View/Edit container (name, description)
 * - View versions list with selection
 * - View selected version template
 * - Create new version via modal
 * - Activate/Archive version
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { promptsApi, type PromptDetail, type PromptVersion, type PromptVersionInfo } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import Modal from '@/shared/ui/Modal';
import Textarea from '@/shared/ui/Textarea';
import styles from './PromptEditorPage.module.css';

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  active: 'Активна',
  archived: 'Архив',
};

const STATUS_TONES: Record<string, 'warning' | 'success' | 'neutral'> = {
  draft: 'warning',
  active: 'success',
  archived: 'neutral',
};

export function PromptEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  // Form state for container
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    type: 'prompt' as 'prompt' | 'baseline',
  });

  // Selected version
  const [selectedVersionNum, setSelectedVersionNum] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // New version modal
  const [showNewVersionModal, setShowNewVersionModal] = useState(false);
  const [newVersionTemplate, setNewVersionTemplate] = useState('');

  // Load prompt container
  const { data: prompt, isLoading, refetch } = useQuery({
    queryKey: qk.prompts.detail(slug!),
    queryFn: () => promptsApi.getPrompt(slug!),
    enabled: !!slug && !isNew,
  });

  // Load selected version details
  const { data: selectedVersion } = useQuery({
    queryKey: ['prompts', slug, 'versions', selectedVersionNum],
    queryFn: () => promptsApi.getVersion(slug!, selectedVersionNum!),
    enabled: !!slug && selectedVersionNum !== null,
  });

  // Sync form data
  useEffect(() => {
    if (prompt) {
      setFormData({
        slug: prompt.slug,
        name: prompt.name,
        description: prompt.description || '',
        type: prompt.type,
      });
      // Select active or latest version
      if (prompt.versions?.length > 0) {
        const activeVersion = prompt.versions.find(v => v.status === 'active');
        setSelectedVersionNum(activeVersion?.version || prompt.versions[0].version);
      }
    }
  }, [prompt]);

  // Mutations
  const createContainerMutation = useMutation({
    mutationFn: () => promptsApi.createContainer(formData),
    onSuccess: (container) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
      showSuccess('Промпт создан');
      navigate(`/admin/prompts/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateContainerMutation = useMutation({
    mutationFn: () => promptsApi.updateContainer(slug!, {
      name: formData.name,
      description: formData.description,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Промпт обновлён');
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  const createVersionMutation = useMutation({
    mutationFn: (template: string) => promptsApi.createVersion(slug!, { template }),
    onSuccess: (version) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess(`Версия ${version.version} создана`);
      setShowNewVersionModal(false);
      setNewVersionTemplate('');
      setSelectedVersionNum(version.version);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания версии'),
  });

  const activateVersionMutation = useMutation({
    mutationFn: (versionId: string) => promptsApi.activateVersion(versionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Версия активирована');
    },
    onError: (err: any) => showError(err?.message || 'Ошибка активации'),
  });

  const archiveVersionMutation = useMutation({
    mutationFn: (versionId: string) => promptsApi.archiveVersion(versionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      showSuccess('Версия архивирована');
    },
    onError: (err: any) => showError(err?.message || 'Ошибка архивации'),
  });

  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        await createContainerMutation.mutateAsync();
      } else {
        await updateContainerMutation.mutateAsync();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/prompts');
    } else {
      if (prompt) {
        setFormData({
          slug: prompt.slug,
          name: prompt.name,
          description: prompt.description || '',
          type: prompt.type,
        });
      }
      setSearchParams({});
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleCreateVersion = () => {
    if (!newVersionTemplate.trim()) {
      showError('Введите текст промпта');
      return;
    }
    createVersionMutation.mutate(newVersionTemplate);
  };

  const handleCreateFromCurrent = () => {
    if (selectedVersion) {
      setNewVersionTemplate(selectedVersion.template);
      setShowNewVersionModal(true);
    }
  };

  // Field definitions
  const containerFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      required: true,
      disabled: !isNew,
      placeholder: 'chat.rag.system',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'RAG System Prompt',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Описание промпта...',
      rows: 2,
    },
    {
      key: 'type',
      label: 'Тип',
      type: 'select',
      disabled: !isNew,
      options: [
        { value: 'prompt', label: 'Prompt (инструкции)' },
        { value: 'baseline', label: 'Baseline (ограничения)' },
      ],
    },
  ];

  return (
    <EntityPage
      mode={mode}
      entityName={prompt?.name || 'Новый промпт'}
      entityTypeLabel="промпта"
      backPath="/admin/prompts"
      loading={!isNew && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      showDelete={false}
    >
      <ContentGrid>
        {/* Container Info - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Контейнер промпта"
          icon="file-text"
          editable={isEditable}
          fields={containerFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Version Template - 1/2 */}
        {!isNew && (
          <ContentBlock
            width="1/2"
            title={selectedVersion ? `Версия ${selectedVersion.version}` : 'Шаблон промпта'}
            icon="code"
          >
            {selectedVersion ? (
              <>
                <div className={styles.versionHeader}>
                  <Badge tone={STATUS_TONES[selectedVersion.status]}>
                    {STATUS_LABELS[selectedVersion.status]}
                  </Badge>
                  <span className={styles.versionDate}>
                    {new Date(selectedVersion.created_at).toLocaleDateString('ru-RU')}
                  </span>
                </div>
                <pre className={styles.templateBlock}>
                  {selectedVersion.template}
                </pre>
                <div className={styles.versionActions}>
                  {selectedVersion.status === 'draft' && (
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => activateVersionMutation.mutate(selectedVersion.id)}
                      disabled={activateVersionMutation.isPending}
                    >
                      Активировать
                    </Button>
                  )}
                  {selectedVersion.status === 'active' && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => archiveVersionMutation.mutate(selectedVersion.id)}
                      disabled={archiveVersionMutation.isPending}
                    >
                      Архивировать
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCreateFromCurrent}
                  >
                    Создать из текущей
                  </Button>
                </div>
              </>
            ) : (
              <div className={styles.emptyVersion}>
                <p>Нет версий промпта</p>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => setShowNewVersionModal(true)}
                >
                  Создать первую версию
                </Button>
              </div>
            )}
          </ContentBlock>
        )}

        {/* Versions Table - 1/2 */}
        {!isNew && (
          <ContentBlock
            width="1/2"
            title="Версии"
            icon="layers"
          >
            {prompt?.versions && prompt.versions.length > 0 ? (
              <>
                <div className={styles.versionsTable}>
                  <table>
                    <thead>
                      <tr>
                        <th>Версия</th>
                        <th>Статус</th>
                        <th>Дата создания</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prompt.versions.map((v: PromptVersionInfo) => (
                        <tr
                          key={v.id}
                          className={selectedVersionNum === v.version ? styles.selected : ''}
                          onClick={() => setSelectedVersionNum(v.version)}
                        >
                          <td>v{v.version}</td>
                          <td>
                            <Badge tone={STATUS_TONES[v.status]} size="small">
                              {STATUS_LABELS[v.status]}
                            </Badge>
                          </td>
                          <td>{new Date(v.created_at).toLocaleDateString('ru-RU')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className={styles.versionActions} style={{ marginTop: '1rem' }}>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowNewVersionModal(true)}
                  >
                    + Новая версия
                  </Button>
                </div>
              </>
            ) : (
              <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>
                Нет версий. Создайте первую версию в блоке справа.
              </p>
            )}
          </ContentBlock>
        )}
      </ContentGrid>

      {/* New Version Modal */}
      <Modal
        open={showNewVersionModal}
        onClose={() => setShowNewVersionModal(false)}
        title="Создать новую версию"
      >
        <div className={styles.modalContent}>
          <p className={styles.modalHint}>
            Новая версия будет создана со статусом "Черновик"
          </p>
          <Textarea
            value={newVersionTemplate}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNewVersionTemplate(e.target.value)}
            placeholder="Введите текст промпта..."
            rows={12}
            className={styles.templateInput}
          />
          <div className={styles.modalActions}>
            <Button
              variant="outline"
              onClick={() => setShowNewVersionModal(false)}
            >
              Отмена
            </Button>
            <Button
              variant="primary"
              onClick={handleCreateVersion}
              disabled={createVersionMutation.isPending}
            >
              {createVersionMutation.isPending ? 'Создание...' : 'Создать'}
            </Button>
          </div>
        </div>
      </Modal>
    </EntityPage>
  );
}

export default PromptEditorPage;
