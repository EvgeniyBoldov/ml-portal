import React from 'react';
import { Outlet, useLocation, Link } from 'react-router-dom';
import styles from './AdminLayout.module.css';

interface AdminLayoutProps {
  children?: React.ReactNode;
}

export function AdminLayout({ children }: AdminLayoutProps) {
  const location = useLocation();

  const navItems = [
    {
      group: 'Users',
      items: [
        { path: '/admin/users', label: 'Users', icon: '👥' },
        { path: '/admin/users/new', label: 'New User', icon: '➕' },
      ],
    },
    {
      group: 'Tenants',
      items: [
        { path: '/admin/tenants', label: 'Tenants', icon: '🏢' },
        { path: '/admin/tenants/new', label: 'New Tenant', icon: '➕' },
      ],
    },
    {
      group: 'System',
      items: [
        { path: '/admin/audit', label: 'Audit Log', icon: '📋' },
        { path: '/admin/settings/email', label: 'Email Settings', icon: '📧' },
      ],
    },
  ];

  const getBreadcrumb = () => {
    const pathSegments = location.pathname.split('/').filter(Boolean);
    const breadcrumbs: Array<{ label: string; path: string }> = [
      { label: 'Admin', path: '/admin' },
    ];

    if (pathSegments.length > 1) {
      const currentPath = pathSegments.slice(0, 2).join('/');
      const currentLabel =
        navItems
          .flatMap(group => group.items)
          .find(item => item.path === `/${currentPath}`)?.label ||
        pathSegments[1] ||
        'Unknown';

      breadcrumbs.push({ label: currentLabel, path: `/${currentPath}` });
    }

    if (pathSegments.length > 2) {
      breadcrumbs.push({
        label: pathSegments[2] || 'Unknown',
        path: location.pathname,
      });
    }

    return breadcrumbs;
  };

  const breadcrumbs = getBreadcrumb();

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h1 className={styles.sidebarTitle}>Administration</h1>
          <p className={styles.sidebarSubtitle}>Manage users and system</p>
        </div>

        <nav className={styles.nav}>
          {navItems.map(group => (
            <div key={group.group} className={styles.navGroup}>
              <div className={styles.navGroupTitle}>{group.group}</div>
              {group.items.map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`${styles.navItem} ${
                    location.pathname === item.path ? styles.active : ''
                  }`}
                >
                  <span className={styles.navItemIcon}>{item.icon}</span>
                  <span className={styles.navItemText}>{item.label}</span>
                </Link>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <nav className={styles.breadcrumb}>
              {breadcrumbs.map((crumb, index) => (
                <React.Fragment key={crumb.path}>
                  {index > 0 && (
                    <span className={styles.breadcrumbSeparator}>/</span>
                  )}
                  {index === breadcrumbs.length - 1 ? (
                    <span className={styles.breadcrumbCurrent}>
                      {crumb.label}
                    </span>
                  ) : (
                    <Link to={crumb.path} className={styles.breadcrumbItem}>
                      {crumb.label}
                    </Link>
                  )}
                </React.Fragment>
              ))}
            </nav>
            <h1 className={styles.headerTitle}>
              {breadcrumbs[breadcrumbs.length - 1]?.label || 'Admin'}
            </h1>
          </div>

          <div className={styles.headerActions}>
            <Link to="/gpt/chat" className={styles.backButton}>
              ← Back to App
            </Link>
          </div>
        </header>

        <div className={styles.content}>{children || <Outlet />}</div>
      </main>
    </div>
  );
}

export default AdminLayout;
