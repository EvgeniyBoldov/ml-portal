/**
 * DefaultsPage - Global defaults for instances, credentials, and permissions
 * Manages system-wide default settings
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, permissionsApi, promptsApi, toolsApi, collectionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage } from '@/shared/ui';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import Switch from '@/shared/ui/Switch';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './FormPage.module.css';

export function DefaultsPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  // Local state for editing permissions
  const [editingPermissions, setEditingPermissions] = useState(false);
  const [toolPermissions, setToolPermissions] = useState<Record<string, boolean>>({});
  const [collectionPermissions, setCollectionPermissions] = useState<Record<string, boolean>>({});

  // Load default instances (scope=default)
  const { data: instances, isLoading: instancesLoading } = useQuery({
    queryKey: qk.toolInstances.list({ scope: 'default' }),
    queryFn: () => toolInstancesApi.list({ scope: 'default' }),
  });

  // Load default policy
  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: qk.permissions.list({ scope: 'default' }),
    queryFn: () => permissionsApi.list({ scope: 'default' }),
  });
  
  // Load baseline prompts
  const { data: prompts } = useQuery({
    queryKey: ['prompts', 'list', { type: 'baseline' }],
    queryFn: () => promptsApi.listPrompts({ type: 'baseline' }),
  });
  
  // Load all tools and collections for permissions editing
  const { data: allTools } = useQuery({
    queryKey: ['tools', 'list'],
    queryFn: () => toolsApi.list(),
  });
  
  const { data: allCollections } = useQuery({
    queryKey: ['collections', 'list'],
    queryFn: () => collectionsApi.list(),
  });

  const defaultPolicy = policies?.find((p: any) => p.scope === 'default');
  const baselinePrompts = prompts || [];

  const isLoading = instancesLoading || policiesLoading;

  // Initialize permissions state when entering edit mode
  const startEditingPermissions = () => {
    const tools: Record<string, boolean> = {};
    const collections: Record<string, boolean> = {};
    
    allTools?.forEach((t: any) => {
      tools[t.slug] = defaultPolicy?.allowed_tools?.includes(t.slug) || false;
    });
    
    allCollections?.items?.forEach((c: any) => {
      collections[c.slug] = defaultPolicy?.allowed_collections?.includes(c.slug) || false;
    });
    
    setToolPermissions(tools);
    setCollectionPermissions(collections);
    setEditingPermissions(true);
  };
  
  // Save permissions mutation
  const savePermissionsMutation = useMutation({
    mutationFn: async () => {
      if (!defaultPolicy) throw new Error('No default policy');
      
      const allowedTools = Object.entries(toolPermissions)
        .filter(([_, allowed]) => allowed)
        .map(([slug]) => slug);
      
      const allowedCollections = Object.entries(collectionPermissions)
        .filter(([_, allowed]) => allowed)
        .map(([slug]) => slug);
      
      return permissionsApi.update(defaultPolicy.id, {
        allowed_tools: allowedTools,
        allowed_collections: allowedCollections,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.list({ scope: 'default' }) });
      showSuccess('Права доступа сохранены');
      setEditingPermissions(false);
    },
    onError: () => showError('Ошибка сохранения прав доступа'),
  });

  if (isLoading) {
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
            <select className={styles.select} style={{ maxWidth: '400px' }}>
              <option value="">Не выбран (агенты используют свой)</option>
              {baselinePrompts.map((p: any) => (
                <option key={p.id} value={p.id}>{p.name} ({p.slug})</option>
              ))}
            </select>
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

      <div className={styles.grid}>
        {/* Default Permissions */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Права доступа по умолчанию</h2>
            <p className={styles.cardDescription}>
              Базовые права для всех пользователей системы
            </p>
          </div>

          {defaultPolicy ? (
            <>
              {!editingPermissions ? (
                <>
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Разрешённые инструменты</label>
                    {defaultPolicy.allowed_tools?.length ? (
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {defaultPolicy.allowed_tools.map((tool: string) => (
                          <Badge key={tool} variant="success">{tool}</Badge>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--muted)' }}>Все запрещены</span>
                    )}
                  </div>

                  <div className={styles.formGroup}>
                    <label className={styles.label}>Разрешённые коллекции</label>
                    {defaultPolicy.allowed_collections?.length ? (
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {defaultPolicy.allowed_collections.map((coll: string) => (
                          <Badge key={coll} variant="success">{coll}</Badge>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--muted)' }}>Все запрещены</span>
                    )}
                  </div>

                  <div className={styles.actions}>
                    <Button variant="outline" onClick={startEditingPermissions}>
                      Редактировать права
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  {/* Tools permissions table */}
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Инструменты</label>
                    <div style={{ border: '1px solid var(--border)', borderRadius: '8px', overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                        <thead>
                          <tr style={{ background: 'var(--bg-subtle)' }}>
                            <th style={{ textAlign: 'left', padding: '8px 12px' }}>Инструмент</th>
                            <th style={{ textAlign: 'center', padding: '8px 12px', width: '100px' }}>Разрешён</th>
                          </tr>
                        </thead>
                        <tbody>
                          {allTools?.map((tool: any) => (
                            <tr key={tool.slug} style={{ borderTop: '1px solid var(--border)' }}>
                              <td style={{ padding: '8px 12px' }}>
                                <strong>{tool.name}</strong>
                                <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{tool.slug}</div>
                              </td>
                              <td style={{ textAlign: 'center', padding: '8px 12px' }}>
                                <Switch
                                  checked={toolPermissions[tool.slug] || false}
                                  onChange={(checked) => setToolPermissions(prev => ({ ...prev, [tool.slug]: checked }))}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Collections permissions table */}
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Коллекции</label>
                    <div style={{ border: '1px solid var(--border)', borderRadius: '8px', overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                        <thead>
                          <tr style={{ background: 'var(--bg-subtle)' }}>
                            <th style={{ textAlign: 'left', padding: '8px 12px' }}>Коллекция</th>
                            <th style={{ textAlign: 'center', padding: '8px 12px', width: '100px' }}>Разрешена</th>
                          </tr>
                        </thead>
                        <tbody>
                          {allCollections?.items?.length ? (
                            allCollections.items.map((coll: any) => (
                              <tr key={coll.slug} style={{ borderTop: '1px solid var(--border)' }}>
                                <td style={{ padding: '8px 12px' }}>
                                  <strong>{coll.name}</strong>
                                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{coll.slug}</div>
                                </td>
                                <td style={{ textAlign: 'center', padding: '8px 12px' }}>
                                  <Switch
                                    checked={collectionPermissions[coll.slug] || false}
                                    onChange={(checked) => setCollectionPermissions(prev => ({ ...prev, [coll.slug]: checked }))}
                                  />
                                </td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={2} style={{ padding: '12px', textAlign: 'center', color: 'var(--muted)' }}>
                                Нет коллекций
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
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

        {/* Default Instances */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Инстансы по умолчанию</h2>
            <p className={styles.cardDescription}>
              Инстансы инструментов, доступные всем пользователям
            </p>
          </div>

          {instances?.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {instances.map(instance => (
                <div
                  key={instance.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.75rem',
                    background: 'var(--color-bg-secondary)',
                    borderRadius: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                      <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                      <line x1="6" y1="6" x2="6.01" y2="6"/>
                      <line x1="6" y1="18" x2="6.01" y2="18"/>
                    </svg>
                    <div>
                      <strong>{instance.tool?.name || 'Unknown'}</strong>
                      <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                        {instance.id.slice(0, 8)}...
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Badge variant={instance.is_active ? 'success' : 'secondary'}>
                      {instance.is_active ? 'Активен' : 'Неактивен'}
                    </Badge>
                    {instance.health_status && (
                      <Badge variant={instance.health_status === 'healthy' ? 'success' : 'error'}>
                        {instance.health_status}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Alert
              variant="info"
              title="Нет инстансов"
              description="Создайте инстансы инструментов в разделе Интеграции → Инстансы"
            />
          )}

          <div className={styles.actions} style={{ marginTop: '1rem' }}>
            <Button
              variant="outline"
              onClick={() => window.location.href = '/admin/instances/new'}
            >
              Добавить инстанс
            </Button>
          </div>
        </div>
      </div>

      {/* Info about hierarchy */}
      <Alert
        variant="info"
        title="Иерархия настроек"
        description="Настройки применяются по иерархии: Пользователь → Тенант → По умолчанию. Более специфичные настройки переопределяют общие."
        style={{ marginTop: '1.5rem' }}
      />
    </AdminPage>
  );
}

export default DefaultsPage;
