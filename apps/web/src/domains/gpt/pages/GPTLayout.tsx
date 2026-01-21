import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import Button from '@shared/ui/Button';
import styles from './GPTLayout.module.css';
import { useAuth } from '@shared/hooks/useAuth';
import ThemeSwitch from '@shared/ui/ThemeSwitch';

export default function GPTLayout() {
  const nav = useNavigate();
  const { logout, user } = useAuth();
  const normalizedRole = (user?.role || '').toLowerCase();
  const isAdmin = normalizedRole === 'admin';
  const canAccessRag = isAdmin || normalizedRole === 'editor';

  // Logo is served from /public/logo.png to avoid bundler import issues.
  const logoSrc = '/logo.png';

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        {/* Left: logo + brand */}
        <div className={styles.brand}>
          <img
            src={logoSrc}
            alt="Почемучка logo"
            onError={e => {
              const el = e.currentTarget as HTMLImageElement;
              el.style.display = 'none';
            }}
          />
          <div className={styles.brandName}>Почемучка</div>
        </div>

        {/* Center: segmented nav (50% header width) */}
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
            </div>
          </div>
        </nav>

        {/* Right: role -> theme -> profile -> admin -> logout */}
        <div className={styles.right}>
          <span className={styles.user}>{user?.role || ''}</span>
          <ThemeSwitch />
          {isAdmin && (
            <Button variant="outline" onClick={() => nav('/admin')}>
              Админка
            </Button>
          )}
          <Button
            variant="ghost"
            onClick={() => nav('/gpt/profile')}
            title="Личный кабинет"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </Button>
          <Button
            variant="ghost"
            onClick={async () => {
              await logout();
              nav('/login');
            }}
          >
            Выйти
          </Button>
        </div>
      </header>

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
