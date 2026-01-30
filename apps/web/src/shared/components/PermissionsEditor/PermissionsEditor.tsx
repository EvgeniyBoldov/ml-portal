/**
 * PermissionsEditor - Reusable component for editing instance permissions
 * 
 * Used in: DefaultsPage, TenantEditorPage, UserDetailPage
 * 
 * New RBAC model: instance_permissions is a map of instance_slug -> 'allowed' | 'denied' | 'undefined'
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { permissionsApi, toolInstancesApi, type PermissionValue } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PermissionsEditor.module.css';

export type PermissionScope = 'default' | 'tenant' | 'user';

interface PermissionsEditorProps {
  scope: PermissionScope;
  scopeId?: string; // tenant_id or user_id
  title?: string;
  readOnly?: boolean;
}

export function PermissionsEditor({ 
  scope, 
  scopeId, 
  title = 'Права доступа',
  readOnly = false 
}: PermissionsEditorProps) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [isEditing, setIsEditing] = useState(false);
  const [instancePermissions, setInstancePermissions] = useState<Record<string, PermissionValue>>({});

  // Load permissions for scope
  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: qk.permissions.list({ scope, ...(scopeId && { [`${scope}_id`]: scopeId }) }),
    queryFn: () => permissionsApi.list({ scope, ...(scopeId && { [`${scope}_id`]: scopeId }) }),
  });

  // Load all tool instances
  const { data: allInstances, isLoading: instancesLoading } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  const policy = policies?.find((p) => p.scope === scope);
  const isLoading = policiesLoading || instancesLoading;

  // Initialize permissions when entering edit mode
  const startEditing = () => {
    const perms: Record<string, PermissionValue> = {};

    allInstances?.forEach((inst) => {
      const currentValue = policy?.instance_permissions?.[inst.slug];
      perms[inst.slug] = currentValue || 'undefined';
    });

    setInstancePermissions(perms);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setInstancePermissions({});
  };

  const cyclePermission = (slug: string) => {
    const current = instancePermissions[slug] || 'undefined';
    const next: PermissionValue = 
      current === 'undefined' ? 'allowed' :
      current === 'allowed' ? 'denied' : 'undefined';
    setInstancePermissions(prev => ({ ...prev, [slug]: next }));
  };

  // Save permissions
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!policy) throw new Error('No policy found');

      // Filter out 'undefined' values for cleaner storage
      const cleanPerms: Record<string, PermissionValue> = {};
      Object.entries(instancePermissions).forEach(([slug, value]) => {
        if (value !== 'undefined') {
          cleanPerms[slug] = value;
        }
      });

      return permissionsApi.update(policy.id, {
        instance_permissions: cleanPerms,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.list({ scope }) });
      showSuccess('Права доступа сохранены');
      setIsEditing(false);
    },
    onError: () => showError('Ошибка сохранения прав'),
  });

  const getPermissionBadge = (value: PermissionValue | undefined) => {
    switch (value) {
      case 'allowed':
        return <Badge tone="success">Разрешён</Badge>;
      case 'denied':
        return <Badge tone="danger">Запрещён</Badge>;
      default:
        return <Badge tone="neutral">Не задано</Badge>;
    }
  };

  if (isLoading) {
    return (
      <div className={styles.card}>
        <h3 className={styles.title}>{title}</h3>
        <Skeleton height={200} />
      </div>
    );
  }

  if (!policy) {
    return (
      <div className={styles.card}>
        <h3 className={styles.title}>{title}</h3>
        <p className={styles.empty}>Политика не найдена для данного scope</p>
      </div>
    );
  }

  const allowedCount = Object.values(
    isEditing ? instancePermissions : (policy.instance_permissions || {})
  ).filter(v => v === 'allowed').length;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h3 className={styles.title}>{title}</h3>
        {!readOnly && !isEditing && (
          <Button variant="outline" size="small" onClick={startEditing}>
            Редактировать
          </Button>
        )}
        {isEditing && (
          <div className={styles.actions}>
            <Button variant="outline" size="small" onClick={cancelEditing}>
              Отмена
            </Button>
            <Button 
              variant="primary" 
              size="small" 
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        )}
      </div>

      {/* Instances Section */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>
          Инстансы инструментов
          <Badge tone="neutral">
            {allowedCount} разрешено / {allInstances?.length || 0} всего
          </Badge>
        </h4>
        <div className={styles.grid}>
          {allInstances?.map((instance) => {
            const permValue = isEditing 
              ? instancePermissions[instance.slug] 
              : policy.instance_permissions?.[instance.slug];

            return (
              <div key={instance.slug} className={styles.item}>
                <div className={styles.itemInfo}>
                  <span className={styles.itemName}>{instance.name}</span>
                  <code className={styles.itemSlug}>{instance.slug}</code>
                  <span className={styles.itemMeta}>{instance.tool_type} • {instance.scope}</span>
                </div>
                {isEditing ? (
                  <Button
                    variant="outline"
                    size="small"
                    onClick={() => cyclePermission(instance.slug)}
                  >
                    {getPermissionBadge(instancePermissions[instance.slug])}
                  </Button>
                ) : (
                  getPermissionBadge(permValue as PermissionValue)
                )}
              </div>
            );
          })}
          {(!allInstances || allInstances.length === 0) && (
            <p className={styles.empty}>Нет инстансов инструментов</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default PermissionsEditor;
