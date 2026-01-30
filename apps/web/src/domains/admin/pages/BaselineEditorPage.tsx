/**
 * BaselineEditorPage - View/Edit/Create baseline container
 * 
 * Architecture:
 * - One page = three modes (View/Edit/Create)
 * - View mode: readonly, safe browsing
 * - Edit mode: editable, sticky footer with Save/Cancel
 * - Create mode: Edit mode with empty data
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { 
  baselinesApi, 
  type BaselineDetail, 
  type CreateBaselineContainerRequest, 
  type UpdateBaselineContainerRequest,
  type BaselineScope,
  type BaselineVersionInfo,
} from '@/shared/api/baselines';
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
  Switch,
} from '@/shared/ui';
import styles from './BaselineEditorPage.module.css';

type Mode = 'view' | 'edit' | 'create';

interface FormData {
  slug: string;
  name: string;
  description: string;
  scope: BaselineScope;
  is_active: boolean;
}

export function BaselineEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = slug === 'new';
  const initialMode = searchParams.get('mode') === 'edit' ? 'edit' : 'view';
  const [mode, setMode] = useState<Mode>(isNew ? 'create' : initialMode);
  const [formData, setFormData] = useState<FormData>({
    slug: '',
    name: '',
    description: '',
    scope: 'default',
    is_active: true,
  });
  const [hasChanges, setHasChanges] = useState(false);

  // === QUERIES ===
  const { data: baseline, isLoading } = useQuery({
    queryKey: qk.baselines.detail(slug!),
    queryFn: () => baselinesApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  // Sync form data with loaded baseline
  useEffect(() => {
    if (baseline && mode === 'view') {
      setFormData({
        slug: baseline.slug,
        name: baseline.name,
        description: baseline.description || '',
        scope: baseline.scope,
        is_active: baseline.is_active,
      });
      setHasChanges(false);
    }
  }, [baseline, mode]);

  // === MUTATIONS ===
  const createMutation = useMutation({
    mutationFn: (data: CreateBaselineContainerRequest) => baselinesApi.createContainer(data),
    onSuccess: (container) => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн создан');
      navigate(`/admin/baselines/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: UpdateBaselineContainerRequest) => baselinesApi.updateContainer(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн обновлён');
      setMode('view');
      setHasChanges(false);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => baselinesApi.delete(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн удалён');
      navigate('/admin/baselines');
    },
    onError: (err: any) => showError(err?.message || 'Ошибка удаления'),
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
      navigate('/admin/baselines');
    } else {
      setMode('view');
      if (baseline) {
        setFormData({
          slug: baseline.slug,
          name: baseline.name,
          description: baseline.description || '',
          scope: baseline.scope,
          is_active: baseline.is_active,
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
        is_active: formData.is_active,
      });
    }
  };

  const handleDelete = () => {
    if (!confirm('Удалить бейслайн? Это действие необратимо.')) return;
    deleteMutation.mutate();
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

  if (!isNew && !baseline) {
    return (
      <PageContent>
        <Alert variant="error" title="Бейслайн не найден">
          Бейслайн с таким slug не существует
        </Alert>
      </PageContent>
    );
  }

  const isEditing = mode === 'edit' || mode === 'create';
  const title = isNew ? 'Создать бейслайн' : baseline!.name;
  const subtitle = isNew ? 'Новый бейслайн' : `${baseline!.slug} • ${baseline!.scope}`;

  const breadcrumbs = [
    { label: 'Админ', href: '/admin' },
    { label: 'Бейслайны', href: '/admin/baselines' },
    { label: isNew ? 'Новый' : baseline!.name },
  ];

  return (
    <PageContent>
      <PageHeader
        title={title}
        subtitle={subtitle}
        backTo="/admin/baselines"
        breadcrumbs={breadcrumbs}
        actions={
          mode === 'view'
            ? [
                {
                  label: 'Редактировать',
                  onClick: handleEdit,
                  variant: 'outline',
                  icon: 'edit',
                },
                {
                  label: 'Удалить',
                  onClick: handleDelete,
                  variant: 'danger',
                  icon: 'trash',
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
                  placeholder="security.no-code"
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
                placeholder="Запрет генерации кода"
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
                placeholder="Ограничения для агента по генерации кода"
                rows={3}
              />
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="scope">Scope</label>
            {mode === 'view' ? (
              <div className={styles.value}>
                <Badge variant={formData.scope === 'default' ? 'default' : formData.scope === 'tenant' ? 'warning' : 'success'}>
                  {formData.scope === 'default' ? 'Default (глобальный)' : formData.scope === 'tenant' ? 'Tenant' : 'User'}
                </Badge>
              </div>
            ) : (
              <>
                <Select
                  id="scope"
                  value={formData.scope}
                  onChange={(e) => updateField('scope', e.target.value as BaselineScope)}
                  options={[
                    { value: 'default', label: 'Default (глобальный)' },
                    { value: 'tenant', label: 'Tenant (для тенанта)' },
                    { value: 'user', label: 'User (для пользователя)' },
                  ]}
                  disabled={!isNew}
                />
                <p className={styles.hint}>
                  {isNew ? 'Default — для всех. Tenant/User — для конкретного тенанта/пользователя.' : 'Scope нельзя изменить'}
                </p>
              </>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="is_active">Активен</label>
            {mode === 'view' ? (
              <div className={styles.value}>
                <Badge variant={formData.is_active ? 'success' : 'default'}>
                  {formData.is_active ? 'Да' : 'Нет'}
                </Badge>
              </div>
            ) : (
              <Switch
                id="is_active"
                checked={formData.is_active}
                onChange={(checked) => updateField('is_active', checked)}
              />
            )}
          </div>

          {!isNew && mode === 'view' && (
            <div className={styles.meta}>
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>Создан:</span>
                <span>{new Date(baseline!.created_at).toLocaleString('ru-RU')}</span>
              </div>
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>Обновлён:</span>
                <span>{new Date(baseline!.updated_at).toLocaleString('ru-RU')}</span>
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
            <>
              <Card className={styles.versionsCard}>
                <h4 className={styles.versionsTitle}>Версии</h4>
                {baseline?.versions && baseline.versions.length > 0 ? (
                  <div className={styles.versionsList}>
                    {baseline.versions.map((v: BaselineVersionInfo) => (
                      <div key={v.id} className={styles.versionItem}>
                        <span className={styles.versionNumber}>v{v.version}</span>
                        <Badge variant={v.status === 'active' ? 'success' : v.status === 'draft' ? 'warning' : 'default'}>
                          {v.status}
                        </Badge>
                        <span className={styles.versionDate}>
                          {new Date(v.created_at).toLocaleDateString('ru-RU')}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className={styles.noVersions}>Нет версий</p>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/admin/baselines/${slug}/versions/new`)}
                  style={{ marginTop: '1rem', width: '100%' }}
                >
                  Создать версию
                </Button>
              </Card>
              <Alert variant="info" title="Версионирование">
                <p>Каждый бейслайн может иметь несколько версий.</p>
                <p>Только одна версия может быть активной.</p>
              </Alert>
            </>
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

export default BaselineEditorPage;
