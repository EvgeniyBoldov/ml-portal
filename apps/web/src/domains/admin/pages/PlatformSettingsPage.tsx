/**
 * PlatformSettingsPage - Global platform configuration (singleton)
 *
 * Tabs: Общие настройки | Модели
 * Uses EntityPageV2 + Tab architecture.
 */
import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { platformApi, type PlatformSettings } from '@/shared/api/platform';
import { policiesApi, type Policy } from '@/shared/api/policies';
import { limitsApi } from '@/shared/api/limits';
import { credentialsApi } from '@/shared/api/credentials';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { ContentBlock, type BreadcrumbItem, DataTable, type DataTableColumn, Badge, Button } from '@/shared/ui';
import { EntityPageV2, Tab, type EntityPageMode } from '@/shared/ui/EntityPage/EntityPageV2';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import { useModels } from '@shared/api/hooks/useAdmin';
import type { Model } from '@shared/api/admin';
import styles from './PlatformSettingsPage.module.css';
import { getStatusProps, MODEL_TYPE_LABELS } from '@/shared/lib/statusConfig';

interface FormData {
  default_policy_id: string;
  default_limit_id: string;
}

export function PlatformSettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';

  const [formData, setFormData] = useState<FormData>({
    default_policy_id: '',
    default_limit_id: '',
  });
  const [saving, setSaving] = useState(false);
  

  // ─── Queries ───────────────────────────────────────────────────────

  const { data: settings, isLoading } = useQuery({
    queryKey: qk.platform.settings(),
    queryFn: () => platformApi.get(),
  });

  const { data: policies = [] } = useQuery({
    queryKey: qk.policies.list({}),
    queryFn: () => policiesApi.list(),
  });

  const { data: limits = [] } = useQuery({
    queryKey: qk.limits.list({}),
    queryFn: () => limitsApi.list(),
  });

  // Models queries
  const { data: modelsData, isLoading: modelsLoading } = useModels({ size: 50 });
  const models = modelsData?.items || [];

  // Credentials query
  const { data: credentials = [] } = useQuery({
    queryKey: qk.credentials.list({ owner_platform: true }),
    queryFn: () => credentialsApi.list({ owner_platform: true }),
  });

  

  // ─── Sync form ─────────────────────────────────────────────────────

  useEffect(() => {
    if (settings) {
      setFormData({
        default_policy_id: settings.default_policy_id || '',
        default_limit_id: settings.default_limit_id || '',
      });
    }
  }, [settings]);


  // ─── Mutations ─────────────────────────────────────────────────────

  const updateMutation = useMutation({
    mutationFn: () =>
      platformApi.update({
        default_policy_id: formData.default_policy_id || null,
        default_limit_id: formData.default_limit_id || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.platform.settings() });
      showSuccess('Настройки платформы обновлены');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });


  // ─── Handlers ──────────────────────────────────────────────────────

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMutation.mutateAsync();
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (settings) {
      setFormData({
        default_policy_id: settings.default_policy_id || '',
        default_limit_id: settings.default_limit_id || '',
      });
    }
    setSearchParams({});
  };


  // ─── Models columns ────────────────────────────────────────────────
  // (click row → navigate to /admin/models/:id)

  const modelsColumns: DataTableColumn<Model>[] = [
    {
      key: 'alias',
      label: 'АЛИАС / ИМЯ',
      sortable: true,
      render: (model: Model) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{model.alias}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{model.name}</span>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'ТИП',
      width: 100,
      sortable: true,
      render: (model: Model) => (
        <Badge tone={model.type === 'llm_chat' ? 'info' : 'success'}>
          {MODEL_TYPE_LABELS[model.type] || model.type}
        </Badge>
      ),
    },
    {
      key: 'provider',
      label: 'ПРОВАЙДЕР',
      sortable: true,
      render: (model: Model) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{model.provider}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{model.provider_model_name}</span>
          {model.instance_name && (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', opacity: 0.7 }}>⇢ {model.instance_name}</span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 120,
      sortable: true,
      render: (model: Model) => (
        <Badge tone={getStatusProps('model', model.status).tone}>
          {getStatusProps('model', model.status).label}
        </Badge>
      ),
    },
    {
      key: 'default_for_type',
      label: 'ПО УМОЛЧ.',
      width: 100,
      sortable: true,
      render: (model: Model) => model.default_for_type ? (
        <Badge tone="success" size="small">По умолч.</Badge>
      ) : (
        <span style={{ color: 'var(--text-secondary)' }}>—</span>
      ),
    },
  ];

  // ─── Helpers ───────────────────────────────────────────────────────

  const getPolicyName = (id: string): string => {
    const p = policies.find((p: Policy) => p.id === id);
    return p ? `${p.name} (${p.slug})` : id ? id.slice(0, 8) + '...' : '—';
  };

  const getLimitName = (id: string): string => {
    const l = limits.find((l: any) => l.id === id);
    return l ? `${l.name} (${l.slug})` : id ? id.slice(0, 8) + '...' : '—';
  };

  // ─── Breadcrumbs ───────────────────────────────────────────────────

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Настройки платформы' },
  ];

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <EntityPageV2
      title="Настройки платформы"
      mode={mode}
      loading={isLoading}
      saving={saving}
      breadcrumbs={breadcrumbs}
      onSave={handleSave}
      onCancel={handleCancel}
    >
      <Tab 
        title="Общие настройки" 
        layout="single" 
        id="general"
        actions={
          mode === 'view' ? [
            <Button key="edit-platform" variant="primary" onClick={() => setSearchParams({ mode: 'edit' })}>
              Редактировать
            </Button>,
          ] : undefined
        }
      >
        <ContentBlock title="Дефолтные настройки" icon="settings">
          <div className={styles.settingsGrid}>
            {/* Default Policy */}
            <div className={styles.settingItem}>
              <label className={styles.label}>Политика по умолчанию</label>
              {mode === 'edit' ? (
                <select
                  className={styles.select}
                  value={formData.default_policy_id}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, default_policy_id: e.target.value }))
                  }
                >
                  <option value="">Не выбрана</option>
                  {policies.map((p: Policy) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.slug})
                    </option>
                  ))}
                </select>
              ) : (
                <div className={styles.value}>
                  {getPolicyName(formData.default_policy_id)}
                </div>
              )}
              <span className={styles.hint}>
                Применяется ко всем агентам, если не переопределена на уровне версии
              </span>
            </div>

            {/* Default Limit */}
            <div className={styles.settingItem}>
              <label className={styles.label}>Лимит по умолчанию</label>
              {mode === 'edit' ? (
                <select
                  className={styles.select}
                  value={formData.default_limit_id}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, default_limit_id: e.target.value }))
                  }
                >
                  <option value="">Не выбран</option>
                  {limits.map((l: any) => (
                    <option key={l.id} value={l.id}>
                      {l.name} ({l.slug})
                    </option>
                  ))}
                </select>
              ) : (
                <div className={styles.value}>
                  {getLimitName(formData.default_limit_id)}
                </div>
              )}
              <span className={styles.hint}>
                Ограничения выполнения по умолчанию: шаги, вызовы, таймауты
              </span>
            </div>
          </div>
        </ContentBlock>
      </Tab>

      <Tab 
        title="Модели" 
        layout="full" 
        id="models"
        actions={[
          <Button key="add-model" variant="primary" onClick={() => navigate('/admin/models/new')}>
            Добавить модель
          </Button>,
        ]}
      >
        <DataTable
          columns={modelsColumns}
          data={models}
          keyField="id"
          loading={modelsLoading}
          emptyText="Модели не найдены. Нажмите «Добавить модель» для создания."
          paginated
          pageSize={20}
          onRowClick={(model: Model) => navigate(`/admin/models/${model.id}`)}
        />
      </Tab>

      <Tab 
        title="Общие доступы" 
        layout="single" 
        id="credentials"
        badge={credentials?.length || 0}
        actions={[
          <Button key="add-credential" variant="primary" onClick={() => navigate('/admin/credentials/new')}>
            + Добавить
          </Button>,
        ]}
      >
        <CredentialsPanel mode="platform" />
      </Tab>

      <Tab 
        title="RBAC" 
        layout="single" 
        id="rbac"
        actions={[
          <Button key="create-rule" variant="primary" onClick={() => navigate('/admin/platform/rbac/new')}>
            Создать правило
          </Button>,
        ]}
      >
        <RBACRulesTable mode="platform" />
      </Tab>
    </EntityPageV2>
  );
}

export default PlatformSettingsPage;
