/**
 * PermissionsEditor - Reusable component for editing tool/collection permissions
 * 
 * Used in: DefaultsPage, TenantEditorPage, UserDetailPage
 */
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { permissionsApi, toolsApi, collectionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Switch from '@/shared/ui/Switch';
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
  const [toolPermissions, setToolPermissions] = useState<Record<string, boolean>>({});
  const [collectionPermissions, setCollectionPermissions] = useState<Record<string, boolean>>({});

  // Load permissions for scope
  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: qk.permissions.list({ scope, ...(scopeId && { [`${scope}_id`]: scopeId }) }),
    queryFn: () => permissionsApi.list({ scope, ...(scopeId && { [`${scope}_id`]: scopeId }) }),
  });

  // Load all tools
  const { data: allTools, isLoading: toolsLoading } = useQuery({
    queryKey: ['tools', 'list'],
    queryFn: () => toolsApi.list(),
  });

  // Load all collections
  const { data: allCollections, isLoading: collectionsLoading } = useQuery({
    queryKey: ['collections', 'list'],
    queryFn: () => collectionsApi.list(),
  });

  const policy = policies?.find((p: any) => p.scope === scope);
  const isLoading = policiesLoading || toolsLoading || collectionsLoading;

  // Initialize permissions when entering edit mode
  const startEditing = () => {
    const tools: Record<string, boolean> = {};
    const collections: Record<string, boolean> = {};

    allTools?.forEach((t: any) => {
      tools[t.slug] = policy?.allowed_tools?.includes(t.slug) || false;
    });

    allCollections?.items?.forEach((c: any) => {
      collections[c.slug] = policy?.allowed_collections?.includes(c.slug) || false;
    });

    setToolPermissions(tools);
    setCollectionPermissions(collections);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setToolPermissions({});
    setCollectionPermissions({});
  };

  // Save permissions
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!policy) throw new Error('No policy found');

      const allowedTools = Object.entries(toolPermissions)
        .filter(([_, allowed]) => allowed)
        .map(([slug]) => slug);

      const allowedCollections = Object.entries(collectionPermissions)
        .filter(([_, allowed]) => allowed)
        .map(([slug]) => slug);

      return permissionsApi.update(policy.id, {
        allowed_tools: allowedTools,
        allowed_collections: allowedCollections,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.list({ scope }) });
      showSuccess('Права доступа сохранены');
      setIsEditing(false);
    },
    onError: () => showError('Ошибка сохранения прав'),
  });

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

      {/* Tools Section */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>
          Инструменты
          <Badge variant="secondary" size="small">
            {isEditing 
              ? Object.values(toolPermissions).filter(Boolean).length
              : policy.allowed_tools?.length || 0
            } / {allTools?.length || 0}
          </Badge>
        </h4>
        <div className={styles.grid}>
          {allTools?.map((tool: any) => {
            const isAllowed = isEditing 
              ? toolPermissions[tool.slug] 
              : policy.allowed_tools?.includes(tool.slug);

            return (
              <div key={tool.slug} className={styles.item}>
                <div className={styles.itemInfo}>
                  <span className={styles.itemName}>{tool.name}</span>
                  <code className={styles.itemSlug}>{tool.slug}</code>
                </div>
                {isEditing ? (
                  <Switch
                    checked={toolPermissions[tool.slug] || false}
                    onChange={(checked) => 
                      setToolPermissions(prev => ({ ...prev, [tool.slug]: checked }))
                    }
                  />
                ) : (
                  <Badge variant={isAllowed ? 'success' : 'secondary'} size="small">
                    {isAllowed ? 'Разрешён' : 'Запрещён'}
                  </Badge>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Collections Section */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>
          Коллекции
          <Badge variant="secondary" size="small">
            {isEditing 
              ? Object.values(collectionPermissions).filter(Boolean).length
              : policy.allowed_collections?.length || 0
            } / {allCollections?.items?.length || 0}
          </Badge>
        </h4>
        <div className={styles.grid}>
          {allCollections?.items?.map((collection: any) => {
            const isAllowed = isEditing 
              ? collectionPermissions[collection.slug] 
              : policy.allowed_collections?.includes(collection.slug);

            return (
              <div key={collection.slug} className={styles.item}>
                <div className={styles.itemInfo}>
                  <span className={styles.itemName}>{collection.name}</span>
                  <code className={styles.itemSlug}>{collection.slug}</code>
                </div>
                {isEditing ? (
                  <Switch
                    checked={collectionPermissions[collection.slug] || false}
                    onChange={(checked) => 
                      setCollectionPermissions(prev => ({ ...prev, [collection.slug]: checked }))
                    }
                  />
                ) : (
                  <Badge variant={isAllowed ? 'success' : 'secondary'} size="small">
                    {isAllowed ? 'Разрешена' : 'Запрещена'}
                  </Badge>
                )}
              </div>
            );
          })}
          {(!allCollections?.items || allCollections.items.length === 0) && (
            <p className={styles.empty}>Нет коллекций</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default PermissionsEditor;
