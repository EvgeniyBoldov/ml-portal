/**
 * PlatformSettingsPage - Global platform configuration (singleton)
 *
 * Shows default policy, limit, and RBAC policy for the platform.
 * Uses EntityPage in view/edit mode.
 */
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { platformApi, type PlatformSettings } from '@/shared/api/platform';
import { policiesApi, type Policy } from '@/shared/api/policies';
import { limitsApi } from '@/shared/api/limits';
import { rbacApi, type RbacPolicy } from '@/shared/api/rbac';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  EntityPage,
  ContentBlock,
  type EntityPageMode,
  type BreadcrumbItem,
} from '@/shared/ui';
import styles from './PlatformSettingsPage.module.css';

interface FormData {
  default_policy_id: string;
  default_limit_id: string;
  default_rbac_policy_id: string;
}

export function PlatformSettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit';

  const [formData, setFormData] = useState<FormData>({
    default_policy_id: '',
    default_limit_id: '',
    default_rbac_policy_id: '',
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

  const { data: rbacPolicies = [] } = useQuery({
    queryKey: qk.rbac.list({}),
    queryFn: () => rbacApi.listPolicies(),
  });

  // ─── Sync form ─────────────────────────────────────────────────────

  useEffect(() => {
    if (settings) {
      setFormData({
        default_policy_id: settings.default_policy_id || '',
        default_limit_id: settings.default_limit_id || '',
        default_rbac_policy_id: settings.default_rbac_policy_id || '',
      });
    }
  }, [settings]);

  // ─── Mutations ─────────────────────────────────────────────────────

  const updateMutation = useMutation({
    mutationFn: () =>
      platformApi.update({
        default_policy_id: formData.default_policy_id || null,
        default_limit_id: formData.default_limit_id || null,
        default_rbac_policy_id: formData.default_rbac_policy_id || null,
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
        default_rbac_policy_id: settings.default_rbac_policy_id || '',
      });
    }
    setSearchParams({});
  };

  // ─── Helpers ───────────────────────────────────────────────────────

  const getPolicyName = (id: string): string => {
    const p = policies.find((p: Policy) => p.id === id);
    return p ? `${p.name} (${p.slug})` : id ? id.slice(0, 8) + '...' : '—';
  };

  const getLimitName = (id: string): string => {
    const l = limits.find((l: any) => l.id === id);
    return l ? `${l.name} (${l.slug})` : id ? id.slice(0, 8) + '...' : '—';
  };

  const getRbacPolicyName = (id: string): string => {
    const r = rbacPolicies.find((r: RbacPolicy) => r.id === id);
    return r ? `${r.name} (${r.slug})` : id ? id.slice(0, 8) + '...' : '—';
  };

  // ─── Breadcrumbs ───────────────────────────────────────────────────

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Настройки платформы' },
  ];

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <EntityPage
      mode={mode}
      entityName="Настройки платформы"
      entityTypeLabel="настроек"
      backPath="/admin"
      breadcrumbs={breadcrumbs}
      loading={isLoading}
      saving={saving}
      onEdit={() => setSearchParams({ mode: 'edit' })}
      onSave={handleSave}
      onCancel={handleCancel}
    >
      <ContentBlock title="Дефолтные настройки" icon="settings">
        <div className={styles.settingsGrid}>
          {/* Default Policy */}
          <div className={styles.settingItem}>
            <label className={styles.label}>Политика по умолчанию</label>
            {isEditable ? (
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
            {isEditable ? (
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

          {/* Default RBAC Policy */}
          <div className={styles.settingItem}>
            <label className={styles.label}>RBAC набор по умолчанию</label>
            {isEditable ? (
              <select
                className={styles.select}
                value={formData.default_rbac_policy_id}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, default_rbac_policy_id: e.target.value }))
                }
              >
                <option value="">Не выбран</option>
                {rbacPolicies.map((r: RbacPolicy) => (
                  <option key={r.id} value={r.id}>
                    {r.name} ({r.slug})
                  </option>
                ))}
              </select>
            ) : (
              <div className={styles.value}>
                {getRbacPolicyName(formData.default_rbac_policy_id)}
              </div>
            )}
            <span className={styles.hint}>
              Набор правил доступа к ресурсам платформы (агенты, инструменты, инстансы)
            </span>
          </div>
        </div>
      </ContentBlock>

      <ContentBlock title="Как это работает" icon="info">
        <div className={styles.infoBlock}>
          <p>
            <strong>Платформа</strong> — это глобальные настройки по умолчанию для всей системы.
            Они применяются, когда на уровне тенанта или пользователя нет переопределений.
          </p>
          <p>
            <strong>Приоритет:</strong> Пользователь → Тенант → Платформа
          </p>
          <ul>
            <li><strong>Политика</strong> — правила поведения агентов</li>
            <li><strong>Лимит</strong> — ограничения выполнения (шаги, таймауты)</li>
            <li><strong>RBAC</strong> — правила доступа к ресурсам (allow/deny)</li>
          </ul>
        </div>
      </ContentBlock>
    </EntityPage>
  );
}

export default PlatformSettingsPage;
