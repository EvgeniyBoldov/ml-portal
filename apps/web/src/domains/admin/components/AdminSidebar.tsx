import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Icon } from '@shared/ui/Icon';
import styles from './AdminSidebar.module.css';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const navigation: NavGroup[] = [
  {
    title: 'Обзор',
    items: [
      { path: '/admin', label: 'Дашборд', icon: 'sparkles' },
    ],
  },
  {
    title: 'Пользователи',
    items: [
      { path: '/admin/users', label: 'Пользователи', icon: 'user' },
      { path: '/admin/tenants', label: 'Тенанты', icon: 'database' },
    ],
  },
  {
    title: 'AI Конфигурация',
    items: [
      { path: '/admin/models', label: 'Модели', icon: 'bot' },
      { path: '/admin/prompts', label: 'Промпты', icon: 'file-text' },
      { path: '/admin/tools', label: 'Инструменты', icon: 'settings' },
      { path: '/admin/agents', label: 'Агенты', icon: 'sparkles' },
      { path: '/admin/collections', label: 'Коллекции', icon: 'database' },
      { path: '/admin/policies', label: 'Политики', icon: 'shield' },
    ],
  },
  {
    title: 'Интеграции',
    items: [
      { path: '/admin/instances', label: 'Инстансы', icon: 'server' },
      { path: '/admin/defaults', label: 'Общие настройки', icon: 'sliders' },
    ],
  },
  {
    title: 'Мониторинг',
    items: [
      { path: '/admin/agent-runs', label: 'Запуски агентов', icon: 'activity' },
      { path: '/admin/routing-logs', label: 'Логи маршрутизации', icon: 'git-branch' },
      { path: '/admin/audit', label: 'Аудит', icon: 'file' },
    ],
  },
];

export function AdminSidebar() {
  const location = useLocation();

  const isActive = (path: string) => {
    if (path === '/admin') {
      return location.pathname === '/admin';
    }
    return location.pathname.startsWith(path);
  };

  return (
    <aside className={styles.sidebar}>
      <nav className={styles.nav}>
        {navigation.map((group) => (
          <div key={group.title} className={styles.group}>
            <div className={styles.groupTitle}>{group.title}</div>
            <ul className={styles.groupItems}>
              {group.items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end={item.path === '/admin'}
                    className={({ isActive: active }) =>
                      `${styles.navItem} ${active || isActive(item.path) ? styles.active : ''}`
                    }
                  >
                    <Icon name={item.icon} size={18} className={styles.navIcon} />
                    <span className={styles.navLabel}>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}
