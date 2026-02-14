import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Icon } from '@shared/ui/Icon';
import styles from './AdminHeader.module.css';

interface Breadcrumb {
  label: string;
  path?: string;
}

const routeLabels: Record<string, string> = {
  '/admin': 'Дашборд',
  '/admin/users': 'Пользователи',
  '/admin/users/new': 'Новый пользователь',
  '/admin/tenants': 'Тенанты',
  '/admin/tenants/new': 'Новый тенант',
  '/admin/models': 'Модели',
  '/admin/models/new': 'Новая модель',
  '/admin/tools': 'Инструменты',
  '/admin/tools/new': 'Новый инструмент',
  '/admin/agents': 'Агенты',
  '/admin/agents/new': 'Новый агент',
  '/admin/audit': 'Аудит',
  '/admin/settings': 'Настройки',
  '/admin/settings/email': 'Email настройки',
};

function getBreadcrumbs(pathname: string): Breadcrumb[] {
  const segments = pathname.split('/').filter(Boolean);
  const breadcrumbs: Breadcrumb[] = [];
  
  let currentPath = '';
  for (let i = 0; i < segments.length; i++) {
    currentPath += '/' + segments[i];
    const label = routeLabels[currentPath] || segments[i];
    
    if (i === segments.length - 1) {
      breadcrumbs.push({ label });
    } else {
      breadcrumbs.push({ label, path: currentPath });
    }
  }
  
  return breadcrumbs;
}

interface AdminHeaderProps {
  title?: string;
  actions?: React.ReactNode;
}

export function AdminHeader({ title, actions }: AdminHeaderProps) {
  const location = useLocation();
  const breadcrumbs = getBreadcrumbs(location.pathname);
  const pageTitle = title || breadcrumbs[breadcrumbs.length - 1]?.label || 'Админ';

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <nav className={styles.breadcrumbs}>
          {breadcrumbs.map((crumb, index) => (
            <React.Fragment key={index}>
              {index > 0 && (
                <Icon name="chevron-right" size={14} className={styles.separator} />
              )}
              {crumb.path ? (
                <Link to={crumb.path} className={styles.breadcrumbLink}>
                  {crumb.label}
                </Link>
              ) : (
                <span className={styles.breadcrumbCurrent}>{crumb.label}</span>
              )}
            </React.Fragment>
          ))}
        </nav>
        <h1 className={styles.title}>{pageTitle}</h1>
      </div>
      
      {actions && (
        <div className={styles.actions}>
          {actions}
        </div>
      )}
    </header>
  );
}
