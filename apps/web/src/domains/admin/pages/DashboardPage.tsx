import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@shared/api/admin';
import { qk } from '@shared/api/keys';
import { AdminHeader, StatCard } from '../components';
import Button from '@shared/ui/Button';
import Badge from '@shared/ui/Badge';
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
    <div className={styles.page}>
      <AdminHeader 
        title="Дашборд" 
        actions={
          <Button onClick={() => window.location.reload()}>
            Обновить
          </Button>
        }
      />

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
          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Последние пользователи</h2>
              <Link to="/admin/users">
                <Button variant="outline" size="small">Все пользователи</Button>
              </Link>
            </div>
            <div className={styles.cardContent}>
              {users?.users?.slice(0, 5).map(user => (
                <div key={user.id} className={styles.listItem}>
                  <div className={styles.listItemMain}>
                    <span className={styles.listItemTitle}>{user.login}</span>
                    <span className={styles.listItemSub}>{user.email || '—'}</span>
                  </div>
                  <Badge tone={user.is_active ? 'success' : 'neutral'}>
                    {user.is_active ? 'Активен' : 'Неактивен'}
                  </Badge>
                </div>
              ))}
              {(!users?.users || users.users.length === 0) && (
                <div className={styles.empty}>Нет пользователей</div>
              )}
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Модели</h2>
              <Link to="/admin/models">
                <Button variant="outline" size="small">Все модели</Button>
              </Link>
            </div>
            <div className={styles.cardContent}>
              {models?.items?.slice(0, 5).map(model => (
                <div key={model.id} className={styles.listItem}>
                  <div className={styles.listItemMain}>
                    <span className={styles.listItemTitle}>{model.alias}</span>
                    <span className={styles.listItemSub}>{model.provider}</span>
                  </div>
                  <div className={styles.listItemBadges}>
                    <Badge tone={model.type === 'llm_chat' ? 'info' : 'success'} size="small">
                      {model.type === 'llm_chat' ? 'LLM' : 'Embed'}
                    </Badge>
                    {model.default_for_type && (
                      <Badge tone="warning" size="small">Default</Badge>
                    )}
                  </div>
                </div>
              ))}
              {(!models?.items || models.items.length === 0) && (
                <div className={styles.empty}>Нет моделей</div>
              )}
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Тенанты</h2>
              <Link to="/admin/tenants">
                <Button variant="outline" size="small">Все тенанты</Button>
              </Link>
            </div>
            <div className={styles.cardContent}>
              {tenants?.items?.slice(0, 5).map(tenant => (
                <div key={tenant.id} className={styles.listItem}>
                  <div className={styles.listItemMain}>
                    <span className={styles.listItemTitle}>{tenant.name}</span>
                    <span className={styles.listItemSub}>{tenant.description || '—'}</span>
                  </div>
                  <Badge tone={tenant.is_active ? 'success' : 'neutral'}>
                    {tenant.is_active ? 'Активен' : 'Неактивен'}
                  </Badge>
                </div>
              ))}
              {(!tenants?.items || tenants.items.length === 0) && (
                <div className={styles.empty}>Нет тенантов</div>
              )}
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Быстрые действия</h2>
            </div>
            <div className={styles.cardContent}>
              <div className={styles.quickActions}>
                <Link to="/admin/users/new" className={styles.quickAction}>
                  <span className={styles.quickActionIcon}>👤</span>
                  <span>Новый пользователь</span>
                </Link>
                <Link to="/admin/tenants/new" className={styles.quickAction}>
                  <span className={styles.quickActionIcon}>🏢</span>
                  <span>Новый тенант</span>
                </Link>
                <Link to="/admin/models/new" className={styles.quickAction}>
                  <span className={styles.quickActionIcon}>🤖</span>
                  <span>Новая модель</span>
                </Link>
                <Link to="/admin/agents/new" className={styles.quickAction}>
                  <span className={styles.quickActionIcon}>🕵️</span>
                  <span>Новый агент</span>
                </Link>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;
