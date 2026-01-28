import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { AppHeader } from '@shared/ui/AppHeader';
import styles from './GPTLayout.module.css';
import { useAuth } from '@shared/hooks/useAuth';

export default function GPTLayout() {
  const nav = useNavigate();
  const { logout, user } = useAuth();
  const normalizedRole = (user?.role || '').toLowerCase();
  const isAdmin = normalizedRole === 'admin';
  const canAccessRag = isAdmin || normalizedRole === 'editor';

  const centerNav = (
    <nav className={styles.nav}>
      <div className={styles.segWrap}>
        <div className={styles.seg}>
          <NavLink
            to="/gpt/chat"
            className={({ isActive }) =>
              [styles.segBtn, isActive ? styles.active : ''].join(' ')
            }
          >
            Чат
          </NavLink>
          {canAccessRag && (
            <NavLink
              to="/gpt/rag"
              className={({ isActive }) =>
                [styles.segBtn, isActive ? styles.active : ''].join(' ')
              }
            >
              База знаний
            </NavLink>
          )}
          {canAccessRag && (
            <NavLink
              to="/gpt/collections"
              className={({ isActive }) =>
                [styles.segBtn, isActive ? styles.active : ''].join(' ')
              }
            >
              Коллекции
            </NavLink>
          )}
        </div>
      </div>
    </nav>
  );

  return (
    <div className={styles.shell}>
      <AppHeader
        brandName="Почемучка"
        variant="default"
        userLabel={user?.role || ''}
        centerContent={centerNav}
        showAdminButton={isAdmin}
        onAdminClick={() => nav('/admin')}
        showProfileButton
        onProfileClick={() => nav('/gpt/profile')}
        onLogout={async () => {
          await logout();
          nav('/login');
        }}
      />

      <main className={styles.main}>
        <Outlet />
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerContent}>
          <a 
            href="https://boldov.dev" 
            target="_blank" 
            rel="noopener noreferrer"
            className={styles.footerLogo}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
            Boldov Development Ltd
          </a>
          <span className={styles.footerDivider}>•</span>
          <span className={styles.footerYear}>© {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}
