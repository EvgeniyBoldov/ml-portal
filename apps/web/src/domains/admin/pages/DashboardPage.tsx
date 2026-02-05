import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@shared/api/admin';
import { qk } from '@shared/api/keys';
import { StatCard } from '../components';
import { AdminPage, EntityCard, QuickAction, QuickActionGrid, Badge, Button } from '@/shared/ui';
import styles from './DashboardPage.module.css';

export function DashboardPage() {
  const { data: users } = useQuery({
    queryKey: qk.admin.users.list({}),
    queryFn: () => adminApi.getUsers({ limit: 5 }),
  });

  const { data: tenants } = useQuery({
    queryKey: qk.admin.tenants.list({}),
    queryFn: () => adminApi.getTenants(),
  });

  const { data: models } = useQuery({
    queryKey: qk.admin.models.list({}),
    queryFn: () => adminApi.getModels({ size: 10 }),
  });

  const totalUsers = users?.total || 0;
  const activeUsers = users?.users?.filter(u => u.is_active).length || 0;
  const totalTenants = tenants?.total || 0;
  const totalModels = models?.total || 0;
  const activeModels = models?.items?.filter(m => m.enabled).length || 0;

  return (
    <AdminPage
      title="Дашборд" 
      subtitle="Обзор системы"
      actions={[
        {
          label: 'Обновить',
          onClick: () => window.location.reload(),
          variant: 'outline',
        }
      ]}
    >
      <div className={styles.content}>
        <section className={styles.stats}>
          <StatCard
            title="Пользователи"
            value={totalUsers}
            icon="users"
            color="primary"
          />
          <StatCard
            title="Активные пользователи"
            value={activeUsers}
            icon="user"
            color="success"
          />
          <StatCard
            title="Тенанты"
            value={totalTenants}
            icon="building"
            color="info"
          />
          <StatCard
            title="Модели"
            value={`${activeModels}/${totalModels}`}
            icon="bot"
            color="warning"
          />
        </section>

        <div className={styles.grid}>
          <EntityCard
            title="Последние пользователи"
            actions={<Button variant="outline" size="small" onClick={() => window.location.href = '/admin/users'}>Все пользователи</Button>}
          >
            {users?.users?.slice(0, 5).map(user => (
              <EntityCard.Item
                key={user.id}
                title={user.login}
                subtitle={user.email || '—'}
                badge={
                  <Badge tone={user.is_active ? 'success' : 'neutral'}>
                    {user.is_active ? 'Активен' : 'Неактивен'}
                  </Badge>
                }
              />
            ))}
            {(!users?.users || users.users.length === 0) && (
              <div className={styles.empty}>Нет пользователей</div>
            )}
          </EntityCard>

          <EntityCard
            title="Модели"
            actions={<Button variant="outline" size="small" onClick={() => window.location.href = '/admin/models'}>Все модели</Button>}
          >
            {models?.items?.slice(0, 5).map(model => (
              <EntityCard.Item
                key={model.id}
                title={model.alias}
                subtitle={model.provider}
                badges={
                  <>
                    <Badge tone={model.type === 'llm_chat' ? 'info' : 'success'}>
                      {model.type === 'llm_chat' ? 'LLM' : 'Embed'}
                    </Badge>
                    {model.default_for_type && (
                      <Badge tone="warn">Default</Badge>
                    )}
                  </>
                }
              />
            ))}
            {(!models?.items || models.items.length === 0) && (
              <div className={styles.empty}>Нет моделей</div>
            )}
          </EntityCard>

          <EntityCard
            title="Тенанты"
            actions={<Button variant="outline" size="small" onClick={() => window.location.href = '/admin/tenants'}>Все тенанты</Button>}
          >
            {tenants?.items?.slice(0, 5).map(tenant => (
              <EntityCard.Item
                key={tenant.id}
                title={tenant.name}
                subtitle={tenant.description || '—'}
                badge={
                  <Badge tone={tenant.is_active ? 'success' : 'neutral'}>
                    {tenant.is_active ? 'Активен' : 'Неактивен'}
                  </Badge>
                }
              />
            ))}
            {(!tenants?.items || tenants.items.length === 0) && (
              <div className={styles.empty}>Нет тенантов</div>
            )}
          </EntityCard>

          <EntityCard title="Быстрые действия">
            <QuickActionGrid>
              <QuickAction icon="👤" label="Новый пользователь" href="/admin/users/new" />
              <QuickAction icon="🏢" label="Новый тенант" href="/admin/tenants/new" />
              <QuickAction icon="🤖" label="Новая модель" href="/admin/models/new" />
              <QuickAction icon="🕵️" label="Новый агент" href="/admin/agents/new" />
            </QuickActionGrid>
          </EntityCard>
        </div>
      </div>
    </AdminPage>
  );
}

export default DashboardPage;
