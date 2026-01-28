/**
 * PromptEntityPage - View/Edit/Create prompt container
 * 
 * Architecture:
 * - One page = three modes (View/Edit/Create)
 * - View mode: readonly, safe browsing
 * - Edit mode: editable, sticky footer with Save/Cancel
 * - Create mode: Edit mode with empty data
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { promptsApi, type PromptDetail, type CreatePromptContainerRequest, type UpdatePromptContainerRequest } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  PageHeader,
  PageContent,
  Card,
  Badge,
  Button,
  Input,
  Textarea,
  Select,
  Skeleton,
  Alert,
} from '@/shared/ui';
import styles from './PromptEntityPage.module.css';

type Mode = 'view' | 'edit' | 'create';

interface FormData {
  slug: string;
  name: string;
  description: string;
  type: 'prompt' | 'baseline';
}

export default function PromptEntityPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = slug === 'new';
  const [mode, setMode] = useState<Mode>(isNew ? 'create' : 'view');
  const [formData, setFormData] = useState<FormData>({
    slug: '',
    name: '',
    description: '',
    type: 'prompt',
  });
  const [hasChanges, setHasChanges] = useState(false);

  // === QUERIES ===
  const { data: prompt, isLoading } = useQuery({
    queryKey: qk.prompts.detail(slug!),
    queryFn: () => promptsApi.getPrompt(slug!),
    enabled: !!slug && !isNew,
  });

  // Sync form data with loaded prompt
  useEffect(() => {
    if (prompt && mode === 'view') {
      setFormData({
        slug: prompt.slug,
        name: prompt.name,
        description: prompt.description || '',
        type: prompt.type,
      });
      setHasChanges(false);
    }
  }, [prompt, mode]);

  // === MUTATIONS ===
  const createMutation = useMutation({
    mutationFn: (data: CreatePromptContainerRequest) => promptsApi.createContainer(data),
    onSuccess: (container) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
      showSuccess('Промпт создан');
      navigate(`/admin/prompts/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: UpdatePromptContainerRequest) => promptsApi.updateContainer(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
      showSuccess('Промпт обновлён');
      setMode('view');
      setHasChanges(false);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  // === HANDLERS ===
  const handleEdit = () => {
    setMode('edit');
  };

  const handleCancel = () => {
    if (hasChanges) {
      if (!confirm('Отменить изменения?')) return;
    }
    
    if (isNew) {
      navigate('/admin/prompts');
    } else {
      setMode('view');
      if (prompt) {
        setFormData({
          slug: prompt.slug,
          name: prompt.name,
          description: prompt.description || '',
          type: prompt.type,
        });
      }
      setHasChanges(false);
    }
  };

  const handleSave = () => {
    if (!formData.name.trim()) {
      showError('Введите название');
      return;
    }

    if (isNew) {
      if (!formData.slug.trim()) {
        showError('Введите slug');
        return;
      }
      createMutation.mutate(formData);
    } else {
      updateMutation.mutate({
        name: formData.name,
        description: formData.description,
      });
    }
  };

  const updateField = <K extends keyof FormData>(field: K, value: FormData[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  // === RENDER ===
  if (isLoading) {
    return (
      <PageContent>
        <Skeleton height={40} width={300} style={{ marginBottom: '1rem' }} />
        <Skeleton height={400} />
      </PageContent>
    );
  }

  if (!isNew && !prompt) {
    return (
      <PageContent>
        <Alert variant="error" title="Промпт не найден">
          Промпт с таким slug не существует
        </Alert>
      </PageContent>
    );
  }

  const isEditing = mode === 'edit' || mode === 'create';
  const title = isNew ? 'Создать промпт' : prompt!.name;
  const subtitle = isNew ? 'Новый контейнер промпта' : `${prompt!.slug} • ${prompt!.type}`;

  return (
    <PageContent>
      <PageHeader
        title={title}
        subtitle={subtitle}
        backTo="/admin/prompts"
        actions={
          mode === 'view'
            ? [
                {
                  label: 'Редактировать',
                  onClick: handleEdit,
                  variant: 'outline',
                  icon: 'edit',
                },
              ]
            : []
        }
      />

      {isEditing && (
        <div className={styles.modeBadge}>
          <Badge variant="warning">Режим редактирования</Badge>
        </div>
      )}

      <div className={styles.grid}>
        <Card className={styles.mainCard}>
          <h3 className={styles.sectionTitle}>Основная информация</h3>

          <div className={styles.field}>
            <label htmlFor="slug">Slug (ID)</label>
            {mode === 'view' ? (
              <div className={styles.value}>
                <code>{formData.slug}</code>
              </div>
            ) : (
              <>
                <Input
                  id="slug"
                  value={formData.slug}
                  onChange={(e) => updateField('slug', e.target.value)}
                  placeholder="chat.rag.system"
                  disabled={!isNew}
                />
                <p className={styles.hint}>
                  {isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : 'Slug нельзя изменить'}
                </p>
              </>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="name">Название</label>
            {mode === 'view' ? (
              <div className={styles.value}>{formData.name}</div>
            ) : (
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="RAG System Prompt"
              />
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="description">Описание</label>
            {mode === 'view' ? (
              <div className={styles.value}>{formData.description || '—'}</div>
            ) : (
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="Системный промпт для RAG агента"
                rows={3}
              />
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="type">Тип</label>
            {mode === 'view' ? (
              <div className={styles.value}>
                <Badge variant={formData.type === 'prompt' ? 'default' : 'warning'}>
                  {formData.type === 'prompt' ? 'Prompt (инструкции)' : 'Baseline (ограничения)'}
                </Badge>
              </div>
            ) : (
              <>
                <Select
                  id="type"
                  value={formData.type}
                  onChange={(e) => updateField('type', e.target.value as 'prompt' | 'baseline')}
                  options={[
                    { value: 'prompt', label: 'Prompt (инструкции)' },
                    { value: 'baseline', label: 'Baseline (ограничения)' },
                  ]}
                  disabled={!isNew}
                />
                <p className={styles.hint}>
                  {isNew ? 'Prompt — основные инструкции. Baseline — ограничения и запреты.' : 'Тип нельзя изменить'}
                </p>
              </>
            )}
          </div>

          {!isNew && mode === 'view' && (
            <div className={styles.meta}>
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>Создан:</span>
                <span>{new Date(prompt!.created_at).toLocaleString('ru-RU')}</span>
              </div>
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>Обновлён:</span>
                <span>{new Date(prompt!.updated_at).toLocaleString('ru-RU')}</span>
              </div>
            </div>
          )}
        </Card>

        <div className={styles.sidebar}>
          {isEditing ? (
            <Alert variant="info" title="Сохранение">
              <p>Изменения будут применены после нажатия кнопки "Сохранить".</p>
              <p>Отмена вернёт все поля к исходным значениям.</p>
            </Alert>
          ) : (
            <Alert variant="info" title="Версии">
              <p>После создания контейнера вы сможете добавить версии с темплейтами.</p>
              <p>Управление версиями доступно на странице детального просмотра.</p>
            </Alert>
          )}
        </div>
      </div>

      {isEditing && (
        <div className={styles.stickyFooter}>
          <Button variant="outline" onClick={handleCancel} disabled={createMutation.isPending || updateMutation.isPending}>
            Отмена
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            {createMutation.isPending || updateMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </div>
      )}
    </PageContent>
  );
}
