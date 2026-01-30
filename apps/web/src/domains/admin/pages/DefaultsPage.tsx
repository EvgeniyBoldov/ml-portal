/**
 * DefaultsPage - Global defaults for instances, credentials, and permissions
 * Manages system-wide default settings
 * 
 * New RBAC model: 
 * - instance_permissions: {instance_slug -> 'allowed' | 'denied'}
 * - agent_permissions: {agent_slug -> 'allowed' | 'denied'}
 */
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { permissionsApi, promptsApi, type PermissionValue } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage, Select, RbacRulesEditor, type RbacPermissions } from '@/shared/ui';
import Button from '@/shared/ui/Button';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './FormPage.module.css';

export function DefaultsPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  // Local state for editing permissions
  const [editingPermissions, setEditingPermissions] = useState(false);
  const [rbacPermissions, setRbacPermissions] = useState<RbacPermissions>({
    instance_permissions: {},
    agent_permissions: {},
  });

  // Load default permission set
  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: qk.permissions.list({ scope: 'default' }),
    queryFn: () => permissionsApi.list({ scope: 'default' }),
  });
  
  // Load baseline prompts
  const { data: prompts } = useQuery({
    queryKey: ['prompts', 'list', { type: 'baseline' }],
    queryFn: () => promptsApi.listPrompts({ type: 'baseline' }),
  });

  const defaultPolicy = policies?.find((p: { scope: string }) => p.scope === 'default');
  const baselinePrompts = prompts || [];

  // Initialize permissions state when entering edit mode
  const startEditingPermissions = () => {
    setRbacPermissions({
      instance_permissions: defaultPolicy?.instance_permissions || {},
      agent_permissions: defaultPolicy?.agent_permissions || {},
    });
    setEditingPermissions(true);
  };

  // Save permissions mutation
  const savePermissionsMutation = useMutation({
    mutationFn: async () => {
      if (!defaultPolicy) throw new Error('No default policy');
      
      return permissionsApi.update(defaultPolicy.id, {
        instance_permissions: rbacPermissions.instance_permissions,
        agent_permissions: rbacPermissions.agent_permissions,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.list({ scope: 'default' }) });
      showSuccess('Права доступа сохранены');
      setEditingPermissions(false);
    },
    onError: () => showError('Ошибка сохранения прав доступа'),
  });

  if (policiesLoading) {
    return (
      <div className={styles.wrap}>
        <Skeleton variant="card" />
      </div>
    );
  }

  return (
    <AdminPage
      title="Общие настройки"
      subtitle="Настройки по умолчанию для всех пользователей системы"
    >
      {/* Default Baseline Prompt */}
      <div className={styles.card} style={{ marginBottom: '1.5rem' }}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>Default Baseline Prompt</h2>
          <p className={styles.cardDescription}>
            Глобальные ограничения для всех агентов (что НЕЛЬЗЯ делать)
          </p>
        </div>
        
        <div className={styles.formGroup}>
          <label className={styles.label}>Baseline промпт по умолчанию</label>
          {baselinePrompts.length > 0 ? (
            <Select
              value=""
              onChange={() => {}}
              placeholder="Не выбран (агенты используют свой)"
              options={[
                { value: '', label: 'Не выбран (агенты используют свой)' },
                ...baselinePrompts.map((p: any) => ({ value: p.id, label: `${p.name} (${p.slug})` }))
              ]}
            />
          ) : (
            <Alert
              variant="info"
              title="Нет baseline промптов"
              description="Создайте baseline промпт в разделе Промпты с типом 'baseline'"
            />
          )}
          <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.5rem' }}>
            Этот baseline будет применяться ко всем агентам, у которых не указан собственный baseline
          </p>
        </div>
      </div>

      {/* Default Permissions - RBAC */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>Права доступа по умолчанию</h2>
          <p className={styles.cardDescription}>
            Базовые права для всех пользователей системы. Новые агенты и инстансы автоматически добавляются как "Запрещён".
          </p>
        </div>

        {defaultPolicy ? (
          <>
            {!editingPermissions ? (
              <>
                <div className={styles.formGroup}>
                  <RbacRulesEditor
                    scope="default"
                    permissions={{
                      instance_permissions: defaultPolicy.instance_permissions || {},
                      agent_permissions: defaultPolicy.agent_permissions || {},
                    }}
                    onChange={() => {}}
                    editable={false}
                  />
                </div>

                <div className={styles.actions}>
                  <Button variant="outline" onClick={startEditingPermissions}>
                    Редактировать права
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className={styles.formGroup}>
                  <RbacRulesEditor
                    scope="default"
                    permissions={rbacPermissions}
                    onChange={setRbacPermissions}
                    editable={true}
                  />
                </div>

                <div className={styles.actions}>
                  <Button variant="outline" onClick={() => setEditingPermissions(false)}>
                    Отмена
                  </Button>
                  <Button 
                    variant="primary" 
                    onClick={() => savePermissionsMutation.mutate()}
                    disabled={savePermissionsMutation.isPending}
                  >
                    {savePermissionsMutation.isPending ? 'Сохранение...' : 'Сохранить'}
                  </Button>
                </div>
              </>
            )}
          </>
        ) : (
          <Alert
            variant="warning"
            title="Политика не найдена"
            description="Default permission set создаётся автоматически при запуске системы"
          />
        )}
      </div>

      {/* Info about hierarchy */}
      <div style={{ marginTop: '1.5rem' }}>
        <Alert
          variant="info"
          title="Иерархия настроек"
          description="Настройки применяются по иерархии: Пользователь → Тенант → По умолчанию. Более специфичные настройки переопределяют общие. Новые объекты автоматически добавляются в default как 'Запрещён'."
        />
      </div>
    </AdminPage>
  );
}

export default DefaultsPage;
