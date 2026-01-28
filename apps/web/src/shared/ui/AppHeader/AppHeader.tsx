/**
 * AppHeader - Unified header component for all layouts
 * 
 * Used in both GPTLayout and AdminLayout.
 * Supports different visual modes via `variant` prop.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../Button';
import ThemeSwitch from '../ThemeSwitch';
import styles from './AppHeader.module.css';

export interface AppHeaderProps {
  /** Brand name displayed next to logo */
  brandName?: string;
  /** Logo image source */
  logoSrc?: string;
  /** Visual variant: 'default' (full-width) or 'contained' (with border-radius) */
  variant?: 'default' | 'contained';
  /** User email or role to display */
  userLabel?: string;
  /** Center content (navigation) */
  centerContent?: React.ReactNode;
  /** Show admin button */
  showAdminButton?: boolean;
  /** Admin button click handler */
  onAdminClick?: () => void;
  /** Show "back to app" button */
  showBackToApp?: boolean;
  /** Back to app click handler */
  onBackToAppClick?: () => void;
  /** Logout handler */
  onLogout?: () => void;
  /** Show profile button */
  showProfileButton?: boolean;
  /** Profile button click handler */
  onProfileClick?: () => void;
}

export function AppHeader({
  brandName = 'ML Portal',
  logoSrc = '/logo.png',
  variant = 'default',
  userLabel,
  centerContent,
  showAdminButton,
  onAdminClick,
  showBackToApp,
  onBackToAppClick,
  onLogout,
  showProfileButton,
  onProfileClick,
}: AppHeaderProps) {
  const headerClass = variant === 'contained' 
    ? `${styles.header} ${styles.contained}` 
    : styles.header;

  return (
    <header className={headerClass}>
      {/* Left: logo + brand */}
      <div className={styles.brand}>
        <img
          src={logoSrc}
          alt={`${brandName} logo`}
          onError={e => {
            const el = e.currentTarget as HTMLImageElement;
            el.style.display = 'none';
          }}
        />
        <div className={styles.brandName}>{brandName}</div>
      </div>

      {/* Center: navigation or spacer to push right content */}
      {centerContent ? (
        <div className={styles.center}>
          {centerContent}
        </div>
      ) : (
        <div className={styles.spacer} />
      )}

      {/* Right: user + theme + actions */}
      <div className={styles.right}>
        {userLabel && <span className={styles.user}>{userLabel}</span>}
        <ThemeSwitch />
        
        {showAdminButton && onAdminClick && (
          <Button variant="outline" onClick={onAdminClick}>
            Админка
          </Button>
        )}
        
        {showBackToApp && onBackToAppClick && (
          <Button variant="outline" onClick={onBackToAppClick}>
            К приложению
          </Button>
        )}
        
        {showProfileButton && onProfileClick && (
          <Button variant="ghost" onClick={onProfileClick} title="Личный кабинет">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </Button>
        )}
        
        {onLogout && (
          <Button variant="ghost" onClick={onLogout}>
            Выход
          </Button>
        )}
      </div>
    </header>
  );
}

export default AppHeader;
